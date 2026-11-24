"""Build a chronological calibration window from the app's stock ledger."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.calibration import CALIBRATION_DAYS, TEST_DAYS, VALIDATION_DAYS, CalibrationDay, CalibrationPlan, make_plan
from app.models.catalog import Product
from app.models.inventory import StockMovement


BUSINESS_ZONE = ZoneInfo("America/Sao_Paulo")
OPERATIONAL_WAREHOUSE = "1"
OPERATIONAL_BASIS = "verified_operational_stock_history"


def _whole(quantity: Decimal) -> bool:
    return quantity == quantity.to_integral_value()


def assess_operational(
    db: Session, product: Product, warehouse: str, today: date, configured_lead_time: int | None = None,
) -> tuple[CalibrationPlan | None, str]:
    """Use complete local dates after a genuine opening balance in the single-stock ledger."""
    if warehouse != OPERATIONAL_WAREHOUSE:
        return None, "operational_warehouse_unavailable"

    sku_movements = select(StockMovement).where(StockMovement.product_id == product.id)
    opening = db.scalar(
        sku_movements.where(
            StockMovement.movement_type == "ENTRADA",
            StockMovement.reason_code == "SALDO_INICIAL",
            StockMovement.is_synthetic.is_(False),
            StockMovement.balance_before == 0,
        ).order_by(StockMovement.id.desc()).limit(1)
    )
    if opening is None or opening.unit_snapshot != "UN":
        return None, "operational_opening_stock_unavailable"

    if (
        opening.balance_after <= 0
        or opening.balance_after != opening.signed_quantity
        or opening.balance_after != opening.quantity
        or not _whole(opening.balance_after)
    ):
        return None, "inconsistent_operational_ledger"

    opening_day = opening.created_at.astimezone(BUSINESS_ZONE).date()
    window_start = today - timedelta(days=CALIBRATION_DAYS + VALIDATION_DAYS + TEST_DAYS)
    if opening_day >= window_start:
        return None, "insufficient_consecutive_history"

    movements_by_day = defaultdict(list)
    movement_days = {opening.id: opening_day}
    censored_days = set()
    reversed_ids = set()
    last_day = opening_day
    for movement in db.scalars(sku_movements.where(StockMovement.id > opening.id).order_by(StockMovement.id)):
        movement_day = movement.created_at.astimezone(BUSINESS_ZONE).date()
        if movement.is_synthetic:
            return None, "synthetic_operational_movements"
        if movement_day < last_day or movement_day > today or movement.unit_snapshot != "UN":
            return None, "inconsistent_operational_ledger"
        last_day = movement_day
        movements_by_day[movement_day].append(movement)
        movement_days[movement.id] = movement_day
        if movement.movement_type == "AJUSTE":
            censored_days.add(movement_day)
        elif movement.movement_type == "ESTORNO":
            original_id = movement.reference_movement_id
            if original_id == opening.id:
                return None, "operational_opening_stock_reversed"
            reversed_ids.add(original_id)
            censored_days.add(movement_day)
            if original_id in movement_days:
                censored_days.add(movement_days[original_id])

    balance = opening.balance_after
    known_days = []
    measured_lead_times = []
    training_last_day = window_start + timedelta(days=CALIBRATION_DAYS - 1)
    cursor = opening_day
    while cursor <= today:
        opening_stock = balance
        day_known = balance > 0 and cursor not in censored_days
        observed_demand = 0
        for movement in movements_by_day[cursor]:
            if (
                movement.balance_before != balance
                or movement.balance_after != balance + movement.signed_quantity
                or movement.balance_after < 0
                or movement.quantity != abs(movement.signed_quantity)
                or not _whole(movement.signed_quantity)
                or movement.movement_type == "SAIDA" and movement.signed_quantity >= 0
                or movement.movement_type == "ENTRADA" and movement.signed_quantity <= 0
            ):
                return None, "inconsistent_operational_ledger"
            balance = movement.balance_after
            day_known = day_known and balance > 0
            if movement.movement_type == "SAIDA" and movement.is_demand:
                observed_demand -= int(movement.signed_quantity)
            if (
                movement.movement_type == "ENTRADA"
                and movement.reason_code == "RECEBIMENTO"
                and movement.id not in reversed_ids
                and cursor <= training_last_day
                and movement.order_date is not None
                and movement.received_date is not None
                and movement.received_date <= training_last_day
            ):
                measured_lead_times.append((movement.received_date - movement.order_date).days)
        if window_start <= cursor < today and day_known:
            known_days.append(CalibrationDay(cursor, observed_demand, opening_stock=int(opening_stock)))
        cursor += timedelta(days=1)

    if balance != product.current_stock:
        return None, "unverified_operational_stock"
    return make_plan(
        product.sku, warehouse, known_days, tuple(measured_lead_times),
        configured_lead_time if configured_lead_time is not None else product.lead_time_days,
        availability_basis=OPERATIONAL_BASIS,
    )
