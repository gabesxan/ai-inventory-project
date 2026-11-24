from dataclasses import replace
from datetime import datetime, time, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from app.ai.operational_calibration import BUSINESS_ZONE, assess_operational
from app.models.catalog import Category, Product
from app.models.inventory import StockMovement
from app.models.replenishment import ReplenishmentRun, ReplenishmentState


@pytest.fixture()
def ledger(db_session, client, admin_headers):
    today = datetime.now(BUSINESS_ZONE).date()
    category = Category(name="Operational fixture")
    db_session.add(category)
    db_session.flush()
    product = Product(name="Operational fixture", sku="OPER-01", unit="UN", category_id=category.id)
    db_session.add(product)
    db_session.commit()

    def post(kind, date_offset, payload, *, synthetic=False):
        reply = client.post(
            f"/api/movements/{kind}", headers=admin_headers, json={"product_id": product.id, **payload},
        )
        assert reply.status_code == 201, reply.text
        movement_id = reply.json()["id"]
        created_at = datetime.combine(today + timedelta(days=date_offset), time(12), BUSINESS_ZONE)
        db_session.execute(update(StockMovement).where(StockMovement.id == movement_id).values(
            created_at=created_at, is_synthetic=synthetic,
        ))
        db_session.commit()

    return product, today, post


def _open_and_receive(ledger):
    _, today, post = ledger
    post("entry", -58, {"quantity": "20", "reason_code": "SALDO_INICIAL"})
    post("exit", -55, {"quantity": "3", "reason_code": "VENDA"})
    post("entry", -54, {
        "quantity": "5", "reason_code": "RECEBIMENTO",
        "order_date": str(today - timedelta(days=56)), "received_date": str(today - timedelta(days=54)),
    })


def test_operational_ledger_excludes_stockout_interrupted_days(db_session, ledger):
    product, today, post = ledger
    _open_and_receive(ledger)
    # A receipt on the same day cannot turn its stockout into a complete demand day.
    post("exit", -15, {"quantity": "22", "reason_code": "VENDA"})
    post("entry", -15, {"quantity": "6", "reason_code": "RECEBIMENTO"})
    db_session.refresh(product)
    assert assess_operational(db_session, product, "1", today) == (None, "insufficient_consecutive_history")


def test_operational_worker_uses_api_movements_and_excludes_synthetic_data(
    db_session, client, admin_headers, ledger, tmp_path,
):
    pytest.importorskip("torch")
    from app.ai.replenishment_worker import WorkerConfig, run_once

    product, today, post = ledger
    engine = db_session.get_bind()
    sessions = sessionmaker(engine, expire_on_commit=False)
    config = WorkerConfig("OPER-01", "1", tmp_path, "operational-fixture", source="operational_calibrated")
    assert run_once(config, engine, sessions) == "insufficient_data"
    assert db_session.get(ReplenishmentState, ("OPER-01", "1")).reason == "operational_opening_stock_unavailable"

    _open_and_receive(ledger)
    # A receipt in the test slice cannot contribute to the fitted replenishment delay.
    post("entry", -8, {
        "quantity": "4", "reason_code": "RECEBIMENTO",
        "order_date": str(today - timedelta(days=17)), "received_date": str(today - timedelta(days=8)),
    })
    post("exit", -7, {"quantity": "2", "reason_code": "VENDA"})
    db_session.refresh(product)
    plan, reason = assess_operational(db_session, product, "1", today)
    assert reason == "eligible"
    assert plan.lead_time_days == 2 and plan.lead_time_source == "measured"
    assert [sum(day.demand for day in group) for group in (plan.calibration, plan.validation, plan.test)] == [3, 0, 2]
    assert [plan.validation[0].opening_stock, plan.test[0].opening_stock] == [22, 22]
    assert assess_operational(db_session, product, "elsewhere", today) == (None, "operational_warehouse_unavailable")

    assert run_once(config, engine, sessions) == "insufficient_data"
    assert db_session.scalar(select(ReplenishmentRun)) is None
    config = replace(config, pipeline=(0, 0))
    assert run_once(config, engine, sessions) == "published"
    run = db_session.scalar(select(ReplenishmentRun))
    assert run.source == "operational_calibrated"
    assert run.configuration["calibration"]["evaluation_initial_pipeline"] == "empty_simulated"
    assert run.configuration["calibration"]["test_initial_stock"] == 22
    assert run.configuration["scenarios"][0]["demand_mean"] == pytest.approx(3 / 28)
    assert run.evaluation["test_runs"] == [f"operational_test/{today - timedelta(days=14)}"]
    result = client.get("/api/reports/comparison?source=operational_calibrated", headers=admin_headers)
    assert result.status_code == 200 and result.json()["total"] == 3
    suggestion = client.get("/api/reports/replenishment?sku=OPER-01&warehouse=1", headers=admin_headers)
    assert suggestion.status_code == 200 and suggestion.json()["items"][0]["source"] == "operational_calibrated"
    assert run_once(config, engine, sessions) == "unchanged"

    post("entry", 0, {"quantity": "2", "reason_code": "RECEBIMENTO"}, synthetic=True)
    assert run_once(config, engine, sessions) == "insufficient_data"
    db_session.expire_all()
    state = db_session.get(ReplenishmentState, ("OPER-01", "1"))
    assert state.reason == "synthetic_operational_movements" and state.snapshot_id is None
