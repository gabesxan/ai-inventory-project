"""Provedores do contrato de previsão (estado sem modelo e simulação demonstrativa)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.ai.contracts import DemandForecastProvider, ForecastInput, ForecastOutput
from app.ai.dataset_builder import build_daily_product_series_df
from app.ai.replenishment import (
    compute_effective_coverage_days,
    compute_replenishment_quantity,
)
from app.models.catalog import Product
from app.models.historical import HistoricalMovement
from app.models.inventory import StockMovement, StockoutPeriod
from app.schemas.ai import (
    DataReadinessSummary,
    PurchaseSuggestionItemOut,
    PurchaseSuggestionsResponse,
)
from app.services.units import quantize_qty


SAO_PAULO_TZ = ZoneInfo("America/Sao_Paulo")


class NoModelProvider:
    """Provedor padrão enquanto nenhum modelo treinado de IA está conectado."""

    model_version = "none"
    is_connected = False

    def predict(self, items: list[ForecastInput]) -> list[ForecastOutput]:
        """Retorna lista vazia pois não há modelo preditivo conectado nesta v1."""
        return []


class MovingAverageSimulationProvider:
    """
    Simulação demonstrativa baseada em média móvel simples sobre dias válidos sem ruptura.

    Usada exclusivamente para ilustrar o fluxo da tela de Sugestões de Compra;
    não representa qualidade preditiva validada.
    """

    model_version = "simulacao-media-movel-v0"
    is_connected = False

    def predict(self, items: list[ForecastInput]) -> list[ForecastOutput]:
        """Calcula média móvel diária causal (<= as_of_date) excluindo dias em ruptura."""
        now = datetime.now(timezone.utc)
        outputs: list[ForecastOutput] = []

        for item in items:
            df = item.history_df
            valid_days = df[
                (df["product_id"] == item.product_id)
                & (df["has_information"] == True)  # noqa: E712
                & (df["had_stockout"] == False)  # noqa: E712
            ]
            history_days_used = int(len(valid_days))

            if history_days_used > 0:
                recent = valid_days.tail(30)
                avg_daily = Decimal(str(recent["observed_demand_qty"].mean()))
                history_days_used = int(len(recent))
            else:
                avg_daily = Decimal("0.000")

            effective_days = compute_effective_coverage_days(
                item.horizon_days, item.lead_time_days
            )
            pred_horizon = quantize_qty(avg_daily * Decimal(item.horizon_days))
            pred_effective = quantize_qty(avg_daily * Decimal(effective_days))

            rec_qty = compute_replenishment_quantity(
                predicted_demand_effective_window=pred_effective,
                current_stock=item.current_stock,
                safety_stock=item.safety_stock,
                open_purchase_orders_qty=item.open_purchase_orders_qty,
                unit=item.unit,
            )

            if history_days_used == 0:
                reason = (
                    "Simulação sem histórico disponível sem ruptura; "
                    "mantida avaliação manual de estoque mínimo."
                )
            elif rec_qty > Decimal("0"):
                reason = (
                    f"Simulação (média móvel de {history_days_used} dias sem ruptura): "
                    f"demanda estimada de {pred_effective} {item.unit} na janela efetiva de "
                    f"{effective_days} dias + segurança ({item.safety_stock}) supera o saldo atual ({item.current_stock})."
                )
            else:
                reason = (
                    f"Simulação (média móvel de {history_days_used} dias): "
                    f"saldo atual ({item.current_stock} {item.unit}) cobre a demanda estimada "
                    f"({pred_effective}) na janela de {effective_days} dias."
                )

            outputs.append(
                ForecastOutput(
                    product_id=item.product_id,
                    sku=item.sku,
                    product_name=item.product_name,
                    unit=item.unit,
                    available_stock=item.current_stock,
                    safety_stock=item.safety_stock,
                    open_purchase_orders_qty=item.open_purchase_orders_qty,
                    lead_time_days=item.lead_time_days,
                    lead_time_source=item.lead_time_source,
                    horizon_days=item.horizon_days,
                    effective_coverage_days=effective_days,
                    predicted_demand_horizon=pred_horizon,
                    predicted_demand_effective_window=pred_effective,
                    recommended_purchase_qty=rec_qty,
                    prediction_interval_low=None,
                    prediction_interval_high=None,
                    model_version=self.model_version,
                    generated_at=now,
                    period_start=item.as_of_date,
                    period_end=item.as_of_date + timedelta(days=item.horizon_days - 1),
                    reason_summary=reason,
                    is_simulated=True,
                    history_days_used=history_days_used,
                )
            )

        return outputs


def _get_data_readiness(db: Session) -> DataReadinessSummary:
    return DataReadinessSummary(
        active_products=db.scalar(
            select(func.count(Product.id)).where(Product.is_active.is_(True))
        )
        or 0,
        operational_movements=db.scalar(select(func.count(StockMovement.id))) or 0,
        operational_demand_events=db.scalar(
            select(func.count(StockMovement.id)).where(StockMovement.is_demand.is_(True))
        )
        or 0,
        historical_study_movements=db.scalar(select(func.count(HistoricalMovement.id))) or 0,
        stockout_periods_recorded=db.scalar(select(func.count(StockoutPeriod.id))) or 0,
    )


def build_purchase_suggestions(
    db: Session,
    *,
    horizon_days: int = 30,
    simulate: bool = False,
) -> PurchaseSuggestionsResponse:
    """Executa o contrato de previsão e devolve recomendações ou estado informativo."""
    safe_horizon = max(1, min(horizon_days, 180))
    readiness = _get_data_readiness(db)
    replenishment_rule_note = (
        "Regra de reposição sem dupla contagem: janela efetiva W = max(Horizonte H, Prazo de Reposição L). "
        "Quantidade sugerida = max(0, Demanda_prevista(W) + Estoque_segurança - (Saldo_atual + Pedidos_abertos))."
    )
    human_decision_notice = (
        "As recomendações têm caráter exclusivamente de apoio à decisão humana; "
        "nenhum pedido de compra é emitido automaticamente pelo sistema."
    )

    provider: DemandForecastProvider = (
        MovingAverageSimulationProvider() if simulate else NoModelProvider()
    )

    if not simulate:
        return PurchaseSuggestionsResponse(
            model_connected=False,
            is_simulated=False,
            model_version=None,
            status_title="Modelo de IA ainda não conectado",
            status_message=(
                "Esta v1 prepara os dados históricos, períodos de ruptura e contratos de entrada/saída. "
                "O treinamento do modelo preditivo ocorrerá na próxima etapa do projeto de IA. "
                "Caso deseje visualizar o layout funcionando, ative a simulação demonstrativa."
            ),
            replenishment_rule_note=replenishment_rule_note,
            human_decision_notice=human_decision_notice,
            horizon_days=safe_horizon,
            data_readiness=readiness,
            items=[],
        )

    today_local = datetime.now(SAO_PAULO_TZ).date()
    series_df = build_daily_product_series_df(db, end_date=today_local)

    products = db.scalars(
        select(Product)
        .options(joinedload(Product.preferred_supplier))
        .where(Product.is_active.is_(True))
        .order_by(Product.name.asc())
    ).all()

    inputs: list[ForecastInput] = []
    for prod in products:
        if prod.lead_time_days is not None:
            lt = prod.lead_time_days
            lt_source = "Produto"
        elif prod.preferred_supplier and prod.preferred_supplier.default_lead_time_days is not None:
            lt = prod.preferred_supplier.default_lead_time_days
            lt_source = "Fornecedor preferencial"
        else:
            lt = 7
            lt_source = "Padrão (7 dias - não cadastrado)"

        inputs.append(
            ForecastInput(
                product_id=prod.id,
                sku=prod.sku,
                product_name=prod.name,
                unit=prod.unit,
                as_of_date=today_local,
                horizon_days=safe_horizon,
                current_stock=prod.current_stock,
                safety_stock=prod.safety_stock,
                lead_time_days=lt,
                lead_time_source=lt_source,
                open_purchase_orders_qty=Decimal("0.000"),
                history_df=series_df,
            )
        )

    outputs = provider.predict(inputs)
    items_out = [
        PurchaseSuggestionItemOut(
            product_id=o.product_id,
            sku=o.sku,
            product_name=o.product_name,
            unit=o.unit,
            available_stock=o.available_stock,
            safety_stock=o.safety_stock,
            open_purchase_orders_qty=o.open_purchase_orders_qty,
            lead_time_days=o.lead_time_days,
            lead_time_source=o.lead_time_source,
            horizon_days=o.horizon_days,
            effective_coverage_days=o.effective_coverage_days,
            predicted_demand_horizon=o.predicted_demand_horizon,
            predicted_demand_effective_window=o.predicted_demand_effective_window,
            recommended_purchase_qty=o.recommended_purchase_qty,
            prediction_interval_low=o.prediction_interval_low,
            prediction_interval_high=o.prediction_interval_high,
            model_version=o.model_version,
            generated_at=o.generated_at,
            period_start=o.period_start,
            period_end=o.period_end,
            reason_summary=o.reason_summary,
            is_simulated=o.is_simulated,
            history_days_used=o.history_days_used,
        )
        for o in outputs
    ]
    items_out.sort(key=lambda i: (-i.recommended_purchase_qty, i.product_name))

    return PurchaseSuggestionsResponse(
        model_connected=False,
        is_simulated=True,
        model_version=provider.model_version,
        status_title="Simulação Demonstrativa Ativa (Média Móvel Simples)",
        status_message=(
            "Atenção: os valores abaixo são uma SIMULAÇÃO DEMONSTRATIVA calculada por média móvel simples "
            "para ilustrar o contrato de recomendação de compras. Eles não utilizam modelo de IA treinado "
            "e não comprovam precisão preditiva."
        ),
        replenishment_rule_note=replenishment_rule_note,
        human_decision_notice=human_decision_notice,
        horizon_days=safe_horizon,
        data_readiness=readiness,
        items=items_out,
    )
