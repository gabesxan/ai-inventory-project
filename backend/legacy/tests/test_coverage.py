"""DB-12 · daily coverage series on FIXTURES."""
from decimal import Decimal as D

from legacy.coverage import build_series, calibration_demand

DAYS = ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]


def make(**kw):
    base = dict(product_key="estoquefacil-fb15/1/produto/10", warehouse_key="estoquefacil-fb15/1/local/1",
                period_start=DAYS[0], period_end=DAYS[-1], source="fixture ledger 2026-11-01..06",
                covered_days=set(DAYS) - {"2026-11-03"},                  # 11-03: the ledger posted nothing
                demand={"2026-11-01": D("4"), "2026-11-05": D("2")}, receipts={"2026-11-02": D("24")})
    base.update(kw)
    return build_series(**base)


def test_missing_day_is_not_zero_demand():
    s = make()
    st = {d.day: d.status for d in s.days}
    assert st["2026-11-03"] == "calendar_gap"
    gap = next(d for d in s.days if d.day == "2026-11-03")
    assert gap.demand is None and not gap.uncensored
    assert st["2026-11-02"] == "zero_unknown_availability"   # covered, but stock unknown: not a true zero


def test_true_zero_requires_coverage_and_known_availability():
    s = make(availability={"2026-11-02": True, "2026-11-03": True}, availability_basis="fixture balances")
    st = {d.day: d.status for d in s.days}
    assert st["2026-11-02"] == "true_zero" and st["2026-11-03"] == "calendar_gap"


def test_known_stockout_is_excluded_from_uncensored_calibration():
    s = make(availability={"2026-11-04": False, "2026-11-06": True}, unknown_days={"2026-11-05"})
    st = {d.day: d.status for d in s.days}
    assert st["2026-11-04"] == "known_stockout" and st["2026-11-05"] == "unknown_quantity"
    assert calibration_demand(s) == [D("4"), D("0")]          # 11-01 sale, 11-06 true zero only


def test_each_series_identifies_its_source_period():
    s = make()
    assert (s.period_start, s.period_end, s.source) == ("2026-11-01", "2026-11-06", "fixture ledger 2026-11-01..06")
    assert [d.day for d in s.days] == DAYS and s.availability_basis == "unknown"
