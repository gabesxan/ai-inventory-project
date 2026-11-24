from dataclasses import replace

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app.ai.calibration import assess
from app.models.replenishment import ReplenishmentRun, ReplenishmentSnapshot, ReplenishmentState
from test_legacy_reports import legacy_report_data


def stage_coverage(db_session, product_id):
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


def test_calibration_excludes_sales_only_evidence_and_uses_confirmed_contiguous_history(
    db_session, legacy_report_data,
):
    product_id = legacy_report_data
    warehouse = "test-warehouse"
    stage_coverage(db_session, product_id)
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


def test_worker_publishes_calibrated_source_only_after_all_evidence_is_present(
    db_session, legacy_report_data, client, admin_headers, tmp_path,
):
    pytest.importorskip("torch")
    from app.ai.replenishment_worker import WorkerConfig, run_once

    product_id = legacy_report_data
    stage_coverage(db_session, product_id)
    db_session.commit()
    config = WorkerConfig(
        "HIST-TEST", "test-warehouse", tmp_path, "legacy-fixture",
        pipeline=None, source="legacy_calibrated", configured_lead_time=2,
    )
    engine = db_session.get_bind()
    sessions = sessionmaker(engine, expire_on_commit=False)
    assert run_once(config, engine, sessions) == "insufficient_data"
    assert db_session.scalar(select(ReplenishmentRun)) is None

    db_session.execute(text("""
        UPDATE legacy_coverage_series SET availability_basis = 'verified_stock_history' WHERE product_id = :id
    """), {"id": product_id})
    db_session.commit()
    assert run_once(config, engine, sessions) == "insufficient_data"
    movement = client.post("/api/movements/entry", headers=admin_headers, json={
        "product_id": product_id, "quantity": "12", "reason_code": "SALDO_INICIAL",
    })
    assert movement.status_code == 201
    assert run_once(config, engine, sessions) == "insufficient_data"
    assert db_session.scalar(select(ReplenishmentRun)) is None

    eligible = replace(config, pipeline=(0, 0))
    assert run_once(eligible, engine, sessions) == "published"
    run = db_session.scalar(select(ReplenishmentRun))
    assert run.source == "legacy_calibrated"
    assert run.configuration["calibration"]["lead_time_source"] == "configured"
    assert len(run.evaluation["test_runs"]) == 1
    state = db_session.get(ReplenishmentState, (config.sku, config.warehouse))
    snapshot = db_session.get(ReplenishmentSnapshot, state.snapshot_id)
    assert snapshot.payload["source"] == "legacy_calibrated"
    assert run_once(eligible, engine, sessions) == "unchanged"
