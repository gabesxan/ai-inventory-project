from sqlalchemy import text

from app.ai.calibration import assess
from test_legacy_reports import legacy_report_data


def test_calibration_excludes_sales_only_evidence_and_uses_confirmed_contiguous_history(
    db_session, legacy_report_data,
):
    product_id = legacy_report_data
    warehouse = "test-warehouse"
    db_session.execute(text("""
        INSERT INTO legacy_coverage_series
            (warehouse_key, product_id, batch_id, period_start, period_end, source, availability_basis,
             days, sale_days, true_zero_days, zero_unknown_availability_days, known_stockout_days,
             unknown_quantity_days, calendar_gap_days)
        VALUES
            ('test-warehouse', :id, 'report-test-batch', DATE '2025-01-01', DATE '2025-02-25',
             'fixture', 'sales_evidence_only', 56, 0, 56, 0, 0, 0, 0)
    """), {"id": product_id})
    db_session.execute(text("""
        INSERT INTO legacy_coverage_ranges (warehouse_key, product_id, start_date, end_date, day_status, batch_id)
        VALUES ('test-warehouse', :id, DATE '2025-01-01', DATE '2025-02-25', 'true_zero', 'report-test-batch')
    """), {"id": product_id})
    assert assess(db_session, warehouse, configured_lead_time=2) == (None, {"no_verified_availability": 1})

    db_session.execute(text("""
        UPDATE legacy_coverage_series SET availability_basis = 'verified_stock_history' WHERE product_id = :id
    """), {"id": product_id})
    assert assess(db_session, warehouse) == (None, {"lead_time_unavailable": 1})
    plan, reasons = assess(db_session, warehouse, configured_lead_time=2)
    assert reasons == {"eligible": 1}
    assert plan.sku == "HIST-TEST" and len(plan.test) == 14
    assert all(day.demand == 0 for day in (*plan.calibration, *plan.validation, *plan.test))
    db_session.rollback()
