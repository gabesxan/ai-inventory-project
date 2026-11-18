"""Serviço de cálculo de indicadores reais e alertas para o painel."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.catalog import Product
from app.models.inventory import StockMovement
from app.schemas.dashboard import (
    DailyChartPoint,
    DailyUnitFlow,
    DashboardOut,
    ReplenishmentAlertItem,
    UnitPeriodSummary,
)
from app.services.exceptions import DomainError
from app.services.units import UNIT_SPECS, quantize_money


SAO_PAULO_TZ = ZoneInfo("America/Sao_Paulo")


def get_dashboard_data(
    db: Session,
    *,
    days: int = 30,
    start_date: date | None = None,
    end_date: date | None = None,
) -> DashboardOut:
    """Calcula indicadores operacionais em tempo real sem somar unidades incompatíveis."""
    today_local = datetime.now(SAO_PAULO_TZ).date()
    if start_date and end_date:
        if end_date < start_date:
            raise DomainError(422, "A data final deve ser igual ou posterior à data inicial.")
        period_start = start_date
        period_end = end_date
    else:
        safe_days = max(1, min(days, 365))
        period_end = today_local
        period_start = today_local - timedelta(days=safe_days - 1)

    if (period_end - period_start).days > 366:
        raise DomainError(422, "O período máximo de consulta do painel é de 366 dias.")

    active_products = db.scalars(
        select(Product)
        .options(joinedload(Product.category), joinedload(Product.preferred_supplier))
        .where(Product.is_active.is_(True))
        .order_by(Product.name.asc())
    ).all()

    active_count = len(active_products)
    out_of_stock_count = 0
    below_min_count = 0
    estimated_value = Decimal("0.00")
    replenishment_items: list[ReplenishmentAlertItem] = []

    for prod in active_products:
        estimated_value += prod.current_stock * prod.unit_cost
        is_zero = prod.current_stock <= Decimal("0")
        is_below = prod.current_stock < prod.min_stock
        if is_zero:
            out_of_stock_count += 1
        if is_below:
            below_min_count += 1

        if is_zero or is_below:
            deficit = max(Decimal("0.000"), prod.min_stock - prod.current_stock)
            status = "OUT_OF_STOCK" if is_zero else "BELOW_MIN"
            lead_time = (
                prod.lead_time_days
                if prod.lead_time_days is not None
                else (
                    prod.preferred_supplier.default_lead_time_days
                    if prod.preferred_supplier
                    else None
                )
            )
            replenishment_items.append(
                ReplenishmentAlertItem(
                    product_id=prod.id,
                    sku=prod.sku,
                    name=prod.name,
                    category_name=prod.category.name if prod.category else "-",
                    unit=prod.unit,
                    current_stock=prod.current_stock,
                    min_stock=prod.min_stock,
                    deficit=deficit,
                    preferred_supplier_name=prod.preferred_supplier.name
                    if prod.preferred_supplier
                    else None,
                    lead_time_days=lead_time,
                    stock_status=status,
                )
            )

    replenishment_items.sort(
        key=lambda item: (0 if item.stock_status == "OUT_OF_STOCK" else 1, -item.deficit, item.name)
    )

    start_utc = datetime.combine(period_start, time.min, tzinfo=SAO_PAULO_TZ).astimezone(
        timezone.utc
    )
    end_utc = datetime.combine(period_end, time.max, tzinfo=SAO_PAULO_TZ).astimezone(
        timezone.utc
    )

    movements = db.scalars(
        select(StockMovement)
        .where(
            StockMovement.created_at >= start_utc,
            StockMovement.created_at <= end_utc,
        )
        .order_by(StockMovement.created_at.asc())
    ).all()

    entries_count = 0
    exits_count = 0
    adjustments_count = 0
    reversals_count = 0

    unit_totals: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {
            "entries": Decimal("0.000"),
            "exits": Decimal("0.000"),
            "demand_exits": Decimal("0.000"),
        }
    )

    daily_counts: dict[date, dict[str, int]] = defaultdict(
        lambda: {"entries_count": 0, "exits_count": 0}
    )
    daily_units: dict[date, dict[str, dict[str, Decimal]]] = defaultdict(
        lambda: defaultdict(lambda: {"entries": Decimal("0.000"), "exits": Decimal("0.000")})
    )

    for mv in movements:
        local_date = mv.created_at.astimezone(SAO_PAULO_TZ).date()
        unit = mv.unit_snapshot

        if mv.movement_type == "ENTRADA":
            entries_count += 1
            unit_totals[unit]["entries"] += mv.quantity
            daily_counts[local_date]["entries_count"] += 1
            daily_units[local_date][unit]["entries"] += mv.quantity
        elif mv.movement_type == "SAIDA":
            exits_count += 1
            unit_totals[unit]["exits"] += mv.quantity
            if mv.is_demand:
                unit_totals[unit]["demand_exits"] += mv.quantity
            daily_counts[local_date]["exits_count"] += 1
            daily_units[local_date][unit]["exits"] += mv.quantity
        elif mv.movement_type == "AJUSTE":
            adjustments_count += 1
        elif mv.movement_type == "ESTORNO":
            reversals_count += 1

    unit_summaries = [
        UnitPeriodSummary(
            unit=unit_code,
            unit_label=UNIT_SPECS.get(unit_code, {}).get("label", unit_code),
            entries_qty=vals["entries"],
            exits_qty=vals["exits"],
            demand_exits_qty=vals["demand_exits"],
        )
        for unit_code, vals in sorted(unit_totals.items())
    ]

    daily_chart: list[DailyChartPoint] = []
    cursor = period_start
    while cursor <= period_end:
        counts = daily_counts[cursor]
        by_unit = {
            u: DailyUnitFlow(entries_qty=vals["entries"], exits_qty=vals["exits"])
            for u, vals in sorted(daily_units[cursor].items())
        }
        daily_chart.append(
            DailyChartPoint(
                date=cursor,
                label=cursor.strftime("%d/%m"),
                entries_count=counts["entries_count"],
                exits_count=counts["exits_count"],
                by_unit=by_unit,
            )
        )
        cursor += timedelta(days=1)

    return DashboardOut(
        active_products_count=active_count,
        out_of_stock_count=out_of_stock_count,
        below_min_stock_count=below_min_count,
        estimated_stock_value_brl=quantize_money(estimated_value),
        valuation_formula="Soma de (saldo atual × custo unitário de referência) dos produtos ativos",
        valuation_disclaimer=(
            "Indicador gerencial aproximado com base no custo de referência cadastrado; "
            "não substitui avaliação contábil ou fiscal (PEPS/custo médio)."
        ),
        period_start=period_start,
        period_end=period_end,
        entries_count=entries_count,
        exits_count=exits_count,
        adjustments_count=adjustments_count,
        reversals_count=reversals_count,
        unit_summaries=unit_summaries,
        daily_chart=daily_chart,
        replenishment_list=replenishment_items,
    )
