from datetime import date, timedelta

from app.ai.calibration import CalibrationDay, make_plan


def history(size=56):
    return [CalibrationDay(date(2025, 1, 1) + timedelta(days=day), day % 7) for day in range(size)]


def test_calibration_uses_chronological_disjoint_partitions_and_measured_lead_time():
    plan, reason = make_plan("A", "1", history(), measured=(3, 2, 4), configured=6)
    assert reason == "eligible"
    assert (len(plan.calibration), len(plan.validation), len(plan.test)) == (28, 14, 14)
    assert plan.calibration[-1].day < plan.validation[0].day < plan.test[0].day
    assert (plan.lead_time_days, plan.lead_time_source) == (3, "measured")
    configured, _ = make_plan("A", "1", history(), configured=2)
    assert (configured.lead_time_days, configured.lead_time_source) == (2, "configured")


def test_a_missing_day_is_never_used_as_zero_and_lead_time_is_required():
    complete = history()
    assert make_plan("A", "1", complete[:10] + complete[11:], configured=1) == (
        None, "insufficient_consecutive_history",
    )
    assert make_plan("A", "1", complete) == (None, "lead_time_unavailable")
