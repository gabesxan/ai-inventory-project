"""Eligibility for legacy calibration, separate from the synthetic worker."""

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median_low

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal


VERIFIED_BASIS = "verified_stock_history"
CALIBRATION_DAYS = 28
VALIDATION_DAYS = 14
TEST_DAYS = 14


@dataclass(frozen=True)
class CalibrationDay:
    day: date
    demand: int


@dataclass(frozen=True)
class CalibrationPlan:
    sku: str
    warehouse: str
    lead_time_days: int
    lead_time_source: str
    calibration: tuple[CalibrationDay, ...]
    validation: tuple[CalibrationDay, ...]
    test: tuple[CalibrationDay, ...]


def make_plan(
    sku: str, warehouse: str, days: list[CalibrationDay], measured: tuple[int, ...] = (),
    configured: int | None = None,
) -> tuple[CalibrationPlan | None, str]:
    """Choose the latest contiguous complete period without filling gaps."""
    required = CALIBRATION_DAYS + VALIDATION_DAYS + TEST_DAYS
    consecutive: list[CalibrationDay] = []
    selected: list[CalibrationDay] = []
    for day in sorted(days, key=lambda item: item.day):
        if consecutive and day.day != consecutive[-1].day + timedelta(days=1):
            consecutive = []
        consecutive.append(day)
        if len(consecutive) >= required:
            selected = consecutive[-required:]
    if not selected:
        return None, "insufficient_consecutive_history"

    arrivals = [days for days in measured if 1 <= days <= 3650]
    if arrivals:
        lead_time, source = median_low(arrivals), "measured"
    elif configured is not None and 1 <= configured <= 3650:
        lead_time, source = configured, "configured"
    else:
        return None, "lead_time_unavailable"
    return CalibrationPlan(
        sku=sku, warehouse=warehouse, lead_time_days=lead_time, lead_time_source=source,
        calibration=tuple(selected[:CALIBRATION_DAYS]),
        validation=tuple(selected[CALIBRATION_DAYS:-TEST_DAYS]),
        test=tuple(selected[-TEST_DAYS:]),
    ), "eligible"


def _confirmed_days(db: Session, product_id: int, warehouse: str) -> list[CalibrationDay]:
    rows = db.execute(text("""
        SELECT dates.day::date AS day, r.day_status, coalesce(sum(h.quantity), 0) AS demand
        FROM legacy_coverage_ranges r
        CROSS JOIN LATERAL generate_series(
            r.start_date::timestamp, r.end_date::timestamp, interval '1 day'
        ) AS dates(day)
        LEFT JOIN legacy_history_events h
          ON h.product_id = r.product_id AND h.warehouse_key = r.warehouse_key
         AND h.event_date = dates.day::date AND h.is_demand
        WHERE r.product_id = :product_id AND r.warehouse_key = :warehouse
          AND r.day_status IN ('sale', 'true_zero')
        GROUP BY day, r.day_status
        ORDER BY day
    """), {"product_id": product_id, "warehouse": warehouse})
    result = []
    for day, status, demand in rows:
        if demand != demand.to_integral_value():
            continue
        if status == "sale" and demand > 0 or status == "true_zero" and demand == Decimal(0):
            result.append(CalibrationDay(day, int(demand)))
    return result


def assess(
    db: Session, warehouse: str, sku: str | None = None, configured_lead_time: int | None = None,
    measured_lead_times: dict[str, tuple[int, ...]] | None = None,
) -> tuple[CalibrationPlan | None, dict[str, int]]:
    """Return one eligible SKU in stable order and report exclusion reasons."""
    rows = db.execute(text("""
        SELECT p.id, p.sku, p.unit, s.availability_basis
        FROM legacy_coverage_series s
        JOIN products p ON p.id = s.product_id
        WHERE s.warehouse_key = :warehouse AND p.is_active
          AND (CAST(:sku AS text) IS NULL OR p.sku = :sku)
        ORDER BY p.sku
    """), {"warehouse": warehouse, "sku": sku})
    reasons: Counter[str] = Counter()
    selected = None
    for product_id, candidate_sku, unit, basis in rows:
        if unit != "UN":
            reasons["non_whole_unit"] += 1
        elif basis != VERIFIED_BASIS:
            # A sale proves units were served, but cannot establish full-day availability.
            reasons["no_verified_availability"] += 1
        else:
            plan, reason = make_plan(
                candidate_sku, warehouse, _confirmed_days(db, product_id, warehouse),
                (measured_lead_times or {}).get(candidate_sku, ()), configured_lead_time,
            )
            reasons[reason] += 1
            if selected is None and plan is not None:
                selected = plan
    if not reasons:
        reasons["no_matching_history"] = 1
    return selected, dict(reasons)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check confirmed Firebird history before calibration.")
    parser.add_argument("--warehouse", required=True)
    parser.add_argument("--sku")
    parser.add_argument("--configured-lead-time", type=int)
    args = parser.parse_args()
    with SessionLocal() as db:
        plan, reasons = assess(db, args.warehouse, args.sku, args.configured_lead_time)
    print(json.dumps({"status": "eligible" if plan else "insufficient_data",
                      "selected": asdict(plan) if plan else None, "reasons": reasons}, default=str))
