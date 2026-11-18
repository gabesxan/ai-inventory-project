"""Construtor de séries diárias e exportações analíticas com pandas para Python/IA."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.catalog import Product
from app.models.historical import HistoricalMovement
from app.models.inventory import StockMovement, StockoutPeriod


SAO_PAULO_TZ = ZoneInfo("America/Sao_Paulo")


def build_daily_product_series_df(
    db: Session,
    *,
    product_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    include_historical: bool = True,
    include_synthetic: bool = True,
) -> pd.DataFrame:
    """
    Constrói DataFrame diário por produto diferenciando:
    - Demanda observada (VENDA/CONSUMO líquidos) vs perdas/avarias/ajustes/estornos
    - Dias com saldo zero (EM_RUPTURA) vs dias disponíveis sem venda vs dias sem informação
    """
    prod_stmt = select(Product).options(joinedload(Product.category)).order_by(Product.id.asc())
    if product_id is not None:
        prod_stmt = prod_stmt.where(Product.id == product_id)
    products = db.scalars(prod_stmt).all()

    columns = [
        "date",
        "product_id",
        "sku",
        "product_name",
        "category_name",
        "unit",
        "is_active",
        "has_information",
        "had_stockout",
        "availability_status",
        "observed_demand_qty",
        "sales_qty",
        "internal_consumption_qty",
        "losses_damages_qty",
        "other_exits_qty",
        "entries_qty",
        "adjustments_net_qty",
        "reversals_net_qty",
        "closing_stock",
        "avg_entry_unit_cost",
        "reference_unit_cost",
        "lead_time_days_config",
        "actual_lead_time_days_avg",
        "data_origin",
        "is_synthetic_data",
    ]
    if not products:
        return pd.DataFrame(columns=columns)

    product_ids = [p.id for p in products]

    op_stmt = (
        select(StockMovement)
        .where(StockMovement.product_id.in_(product_ids))
        .order_by(StockMovement.created_at.asc(), StockMovement.id.asc())
    )
    if not include_synthetic:
        op_stmt = op_stmt.where(StockMovement.is_synthetic.is_(False))
    op_movements = db.scalars(op_stmt).all()
    op_by_id = {m.id: m for m in op_movements}

    hist_movements: list[HistoricalMovement] = []
    if include_historical:
        hist_stmt = (
            select(HistoricalMovement)
            .where(HistoricalMovement.product_id.in_(product_ids))
            .order_by(HistoricalMovement.occurred_at.asc(), HistoricalMovement.id.asc())
        )
        if not include_synthetic:
            hist_stmt = hist_stmt.where(HistoricalMovement.is_synthetic.is_(False))
        hist_movements = db.scalars(hist_stmt).all()

    stockouts = db.scalars(
        select(StockoutPeriod).where(StockoutPeriod.product_id.in_(product_ids))
    ).all()

    today_local = datetime.now(SAO_PAULO_TZ).date()
    effective_end = end_date or today_local

    # Agrupamento por (product_id, local_date)
    op_by_prod_day: dict[tuple[int, date], list[StockMovement]] = defaultdict(list)
    earliest_op_day: dict[int, date] = {}
    for mv in op_movements:
        d = mv.created_at.astimezone(SAO_PAULO_TZ).date()
        op_by_prod_day[(mv.product_id, d)].append(mv)
        if mv.product_id not in earliest_op_day or d < earliest_op_day[mv.product_id]:
            earliest_op_day[mv.product_id] = d

    hist_by_prod_day: dict[tuple[int, date], list[HistoricalMovement]] = defaultdict(list)
    earliest_hist_day: dict[int, date] = {}
    for hm in hist_movements:
        d = hm.occurred_at.astimezone(SAO_PAULO_TZ).date()
        hist_by_prod_day[(hm.product_id, d)].append(hm)
        if hm.product_id not in earliest_hist_day or d < earliest_hist_day[hm.product_id]:
            earliest_hist_day[hm.product_id] = d

    stockout_ranges_by_prod: dict[int, list[tuple[date, date]]] = defaultdict(list)
    for sp in stockouts:
        s_day = sp.started_at.astimezone(SAO_PAULO_TZ).date()
        e_day = (
            sp.ended_at.astimezone(SAO_PAULO_TZ).date()
            if sp.ended_at is not None
            else effective_end
        )
        stockout_ranges_by_prod[sp.product_id].append((s_day, e_day))

    rows: list[dict] = []

    for prod in products:
        created_day = prod.created_at.astimezone(SAO_PAULO_TZ).date()
        candidates = [created_day]
        if prod.id in earliest_op_day:
            candidates.append(earliest_op_day[prod.id])
        if prod.id in earliest_hist_day:
            candidates.append(earliest_hist_day[prod.id])
        first_known_day = min(candidates)

        series_start = start_date if start_date is not None else first_known_day
        if series_start > effective_end:
            continue

        running_op_stock: Decimal | None = None
        last_hist_stock: Decimal | None = None

        # Se a série começar depois do início operacional, pré-computa o saldo na véspera
        if prod.id in earliest_op_day and earliest_op_day[prod.id] < series_start:
            prior_ops = [
                m
                for m in op_movements
                if m.product_id == prod.id
                and m.created_at.astimezone(SAO_PAULO_TZ).date() < series_start
            ]
            if prior_ops:
                running_op_stock = prior_ops[-1].balance_after

        cursor = series_start
        while cursor <= effective_end:
            day_ops = op_by_prod_day.get((prod.id, cursor), [])
            day_hists = hist_by_prod_day.get((prod.id, cursor), [])

            has_info = cursor >= first_known_day
            sales_qty = Decimal("0.000")
            consumption_qty = Decimal("0.000")
            losses_qty = Decimal("0.000")
            other_exits_qty = Decimal("0.000")
            entries_qty = Decimal("0.000")
            adj_net = Decimal("0.000")
            rev_net = Decimal("0.000")
            demand_reversal_sub = Decimal("0.000")
            entry_costs: list[Decimal] = []
            lead_times: list[int] = []
            synthetic_flag = False
            origins: set[str] = set()
            had_hist_stockout = False

            for hm in day_hists:
                origins.add("IMPORTACAO_HISTORICA")
                if hm.is_synthetic:
                    synthetic_flag = True
                if hm.had_stockout:
                    had_hist_stockout = True
                if hm.closing_stock_reported is not None:
                    last_hist_stock = hm.closing_stock_reported
                if hm.movement_type == "ENTRADA":
                    entries_qty += hm.quantity
                    if hm.unit_cost is not None:
                        entry_costs.append(hm.unit_cost)
                    if hm.order_date and hm.received_date:
                        lead_times.append((hm.received_date - hm.order_date).days)
                elif hm.movement_type == "SAIDA":
                    if hm.reason_code == "VENDA":
                        sales_qty += hm.quantity
                    elif hm.reason_code == "CONSUMO":
                        consumption_qty += hm.quantity
                    elif hm.reason_code in ("PERDA", "AVARIA"):
                        losses_qty += hm.quantity
                    else:
                        other_exits_qty += hm.quantity
                elif hm.movement_type == "AJUSTE":
                    if hm.reason_code == "AJUSTE_POSITIVO":
                        adj_net += hm.quantity
                    else:
                        adj_net -= hm.quantity

            for mv in day_ops:
                origins.add("OPERACIONAL")
                if mv.is_synthetic:
                    synthetic_flag = True
                running_op_stock = mv.balance_after
                if mv.movement_type == "ENTRADA":
                    entries_qty += mv.quantity
                    if mv.unit_cost is not None:
                        entry_costs.append(mv.unit_cost)
                    if mv.order_date and mv.received_date:
                        lead_times.append((mv.received_date - mv.order_date).days)
                elif mv.movement_type == "SAIDA":
                    if mv.reason_code == "VENDA":
                        sales_qty += mv.quantity
                    elif mv.reason_code == "CONSUMO":
                        consumption_qty += mv.quantity
                    elif mv.reason_code in ("PERDA", "AVARIA"):
                        losses_qty += mv.quantity
                    else:
                        other_exits_qty += mv.quantity
                elif mv.movement_type == "AJUSTE":
                    adj_net += mv.signed_quantity
                elif mv.movement_type == "ESTORNO":
                    rev_net += mv.signed_quantity
                    ref = op_by_id.get(mv.reference_movement_id) if mv.reference_movement_id else None
                    if ref and ref.is_demand:
                        demand_reversal_sub += mv.quantity

            if not has_info:
                closing_stock: Decimal | None = None
            elif running_op_stock is not None:
                closing_stock = running_op_stock
            elif cursor >= created_day and (prod.id not in earliest_op_day or cursor < earliest_op_day[prod.id]):
                # Se ainda não houve movimentação operacional até este dia, o saldo operacional inicial é 0
                closing_stock = last_hist_stock if last_hist_stock is not None else Decimal("0.000")
            else:
                closing_stock = last_hist_stock

            observed_demand = max(
                Decimal("0.000"),
                (sales_qty + consumption_qty) - demand_reversal_sub,
            )

            overlap_stockout = any(
                s_day <= cursor <= e_day for s_day, e_day in stockout_ranges_by_prod.get(prod.id, [])
            )
            had_stockout = bool(
                overlap_stockout
                or had_hist_stockout
                or (has_info and closing_stock is not None and closing_stock == Decimal("0"))
            )

            if not has_info:
                availability_status = "SEM_INFORMACAO"
            elif had_stockout and observed_demand == Decimal("0"):
                availability_status = "EM_RUPTURA"
            elif observed_demand > Decimal("0"):
                availability_status = "DISPONIVEL_COM_DEMANDA"
            elif had_stockout:
                availability_status = "EM_RUPTURA"
            else:
                availability_status = "DISPONIVEL_SEM_DEMANDA"

            avg_entry_cost = (
                round(float(sum(entry_costs) / len(entry_costs)), 2) if entry_costs else None
            )
            avg_lt = round(sum(lead_times) / len(lead_times), 2) if lead_times else None

            rows.append(
                {
                    "date": cursor.isoformat(),
                    "product_id": prod.id,
                    "sku": prod.sku,
                    "product_name": prod.name,
                    "category_name": prod.category.name if prod.category else "",
                    "unit": prod.unit,
                    "is_active": prod.is_active,
                    "has_information": has_info,
                    "had_stockout": had_stockout if has_info else None,
                    "availability_status": availability_status,
                    "observed_demand_qty": float(observed_demand),
                    "sales_qty": float(sales_qty),
                    "internal_consumption_qty": float(consumption_qty),
                    "losses_damages_qty": float(losses_qty),
                    "other_exits_qty": float(other_exits_qty),
                    "entries_qty": float(entries_qty),
                    "adjustments_net_qty": float(adj_net),
                    "reversals_net_qty": float(rev_net),
                    "closing_stock": float(closing_stock) if closing_stock is not None else None,
                    "avg_entry_unit_cost": avg_entry_cost,
                    "reference_unit_cost": float(prod.unit_cost),
                    "lead_time_days_config": prod.lead_time_days,
                    "actual_lead_time_days_avg": avg_lt,
                    "data_origin": "+".join(sorted(origins)) if origins else ("SEM_MOVIMENTO" if has_info else "SEM_INFORMACAO"),
                    "is_synthetic_data": synthetic_flag,
                }
            )
            cursor += timedelta(days=1)

    return pd.DataFrame(rows, columns=columns)


def export_daily_series_csv(
    db: Session,
    *,
    product_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    include_historical: bool = True,
    include_synthetic: bool = True,
) -> bytes:
    """Exporta visão diária por produto para leitura direta com pandas.read_csv()."""
    df = build_daily_product_series_df(
        db,
        product_id=product_id,
        start_date=start_date,
        end_date=end_date,
        include_historical=include_historical,
        include_synthetic=include_synthetic,
    )
    return df.to_csv(index=False).encode("utf-8-sig")


def export_analytical_movements_csv(
    db: Session,
    *,
    include_historical: bool = True,
    include_synthetic: bool = True,
) -> bytes:
    """Exporta base unificada de movimentações (operacionais + importadas) para análise Python."""
    op_stmt = (
        select(StockMovement)
        .options(joinedload(StockMovement.product), joinedload(StockMovement.supplier))
        .order_by(StockMovement.created_at.asc(), StockMovement.id.asc())
    )
    if not include_synthetic:
        op_stmt = op_stmt.where(StockMovement.is_synthetic.is_(False))
    op_rows = db.scalars(op_stmt).all()

    records: list[dict] = []
    for mv in op_rows:
        actual_lt = (
            (mv.received_date - mv.order_date).days
            if mv.order_date and mv.received_date
            else None
        )
        records.append(
            {
                "record_source": "OPERACIONAL",
                "record_id": f"OP-{mv.id}",
                "occurred_at": mv.created_at.astimezone(SAO_PAULO_TZ).isoformat(),
                "product_id": mv.product_id,
                "sku": mv.product.sku,
                "product_name": mv.product.name,
                "product_active": mv.product.is_active,
                "movement_type": mv.movement_type,
                "reason_code": mv.reason_code,
                "is_demand": mv.is_demand,
                "quantity": float(mv.quantity),
                "signed_quantity": float(mv.signed_quantity),
                "unit": mv.unit_snapshot,
                "unit_cost": float(mv.unit_cost) if mv.unit_cost is not None else None,
                "supplier_name": mv.supplier.name if mv.supplier else None,
                "order_date": mv.order_date.isoformat() if mv.order_date else None,
                "received_date": mv.received_date.isoformat() if mv.received_date else None,
                "actual_lead_time_days": actual_lt,
                "balance_after": float(mv.balance_after),
                "reference_movement_id": mv.reference_movement_id,
                "is_synthetic": mv.is_synthetic,
            }
        )

    if include_historical:
        hist_stmt = (
            select(HistoricalMovement)
            .options(joinedload(HistoricalMovement.product))
            .order_by(HistoricalMovement.occurred_at.asc(), HistoricalMovement.id.asc())
        )
        if not include_synthetic:
            hist_stmt = hist_stmt.where(HistoricalMovement.is_synthetic.is_(False))
        for hm in db.scalars(hist_stmt).all():
            actual_lt = (
                (hm.received_date - hm.order_date).days
                if hm.order_date and hm.received_date
                else None
            )
            signed = (
                hm.quantity
                if hm.movement_type == "ENTRADA" or hm.reason_code == "AJUSTE_POSITIVO"
                else -hm.quantity
            )
            records.append(
                {
                    "record_source": "IMPORTACAO_HISTORICA",
                    "record_id": f"HIST-{hm.id}",
                    "occurred_at": hm.occurred_at.astimezone(SAO_PAULO_TZ).isoformat(),
                    "product_id": hm.product_id,
                    "sku": hm.product.sku,
                    "product_name": hm.product.name,
                    "product_active": hm.product.is_active,
                    "movement_type": hm.movement_type,
                    "reason_code": hm.reason_code,
                    "is_demand": hm.is_demand,
                    "quantity": float(hm.quantity),
                    "signed_quantity": float(signed),
                    "unit": hm.unit_snapshot,
                    "unit_cost": float(hm.unit_cost) if hm.unit_cost is not None else None,
                    "supplier_name": hm.supplier_name,
                    "order_date": hm.order_date.isoformat() if hm.order_date else None,
                    "received_date": hm.received_date.isoformat() if hm.received_date else None,
                    "actual_lead_time_days": actual_lt,
                    "balance_after": (
                        float(hm.closing_stock_reported)
                        if hm.closing_stock_reported is not None
                        else None
                    ),
                    "reference_movement_id": None,
                    "is_synthetic": hm.is_synthetic,
                }
            )

    df = pd.DataFrame(records)
    if df.empty:
        df = pd.DataFrame(
            columns=[
                "record_source",
                "record_id",
                "occurred_at",
                "product_id",
                "sku",
                "product_name",
                "product_active",
                "movement_type",
                "reason_code",
                "is_demand",
                "quantity",
                "signed_quantity",
                "unit",
                "unit_cost",
                "supplier_name",
                "order_date",
                "received_date",
                "actual_lead_time_days",
                "balance_after",
                "reference_movement_id",
                "is_synthetic",
            ]
        )
    else:
        df = df.sort_values(by="occurred_at", ascending=True)
    return df.to_csv(index=False).encode("utf-8-sig")
