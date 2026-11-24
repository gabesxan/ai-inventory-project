from dataclasses import replace

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker

from app.ai.publication import record_status
from app.models.catalog import Category, Product
from app.models.replenishment import ReplenishmentRun, ReplenishmentSnapshot, ReplenishmentState

pytest.importorskip("torch")

from app.ai import replenishment_worker as worker


def test_worker_locks_recovers_and_reuses_training_after_stock_and_pipeline_changes(
    db_session, tmp_path, monkeypatch
):
    config = worker.WorkerConfig("DEMO-TEST", "1", tmp_path, "worker-test")
    engine = db_session.get_bind()
    sessions = sessionmaker(engine, expire_on_commit=False)
    category = Category(name="Replenishment test")
    db_session.add(category)
    db_session.flush()
    product = Product(name="Test item", sku=config.sku, unit="UN", category_id=category.id, current_stock=5)
    db_session.add(product)
    db_session.commit()

    with engine.connect() as competitor:
        competitor.execute(text("SELECT pg_advisory_lock(:key)"), {"key": worker.LOCK_ID})
        assert worker.run_once(config, engine, sessions) == "locked"
        competitor.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": worker.LOCK_ID})
    assert worker.run_once(config, engine, sessions) == "published"
    state_key = config.sku, config.warehouse
    state = db_session.get(ReplenishmentState, state_key)
    first_id = state.snapshot_id
    first_run = db_session.get(ReplenishmentSnapshot, first_id).run_id

    product.current_stock = 12
    record_status(db_session, *state_key, "calculating")
    db_session.commit()
    assert worker.run_once(config, engine, sessions) == "published"
    db_session.refresh(state)
    assert state.status == "ready"
    assert state.snapshot_id != first_id
    assert db_session.get(ReplenishmentSnapshot, state.snapshot_id).run_id == first_run
    assert db_session.scalar(select(func.count()).select_from(ReplenishmentRun)) == 1
    assert worker.run_once(config, engine, sessions) == "unchanged"

    config = replace(config, pipeline=(1, 0, 0, 0, 0))
    assert worker.run_once(config, engine, sessions) == "published"
    db_session.refresh(state)
    latest_id = state.snapshot_id

    def fail(_):
        raise RuntimeError("test failure")

    monkeypatch.setattr(worker, "load_checkpoint", fail)
    with pytest.raises(RuntimeError, match="test failure"):
        worker.run_once(replace(config, pipeline=(2, 0, 0, 0, 0)), engine, sessions)
    db_session.refresh(state)
    assert state.status == "failed"
    assert state.snapshot_id == latest_id
    assert db_session.scalar(select(func.count()).select_from(ReplenishmentSnapshot)) == 3
