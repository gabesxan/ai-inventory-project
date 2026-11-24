import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.publication import publish, record_status
from app.models.replenishment import ReplenishmentRun, ReplenishmentSnapshot, ReplenishmentState
from app.schemas.reports import ReplenishmentRow


def fixture_suggestion() -> ReplenishmentRow:
    fixtures = Path(__file__).resolve().parents[2] / "docs/contracts/report-v1/fixtures.json"
    return ReplenishmentRow.model_validate(json.loads(fixtures.read_text())["ready"]["body"]["items"][0])


def test_publication_has_atomic_visibility_and_preserves_last_good_on_rollback(db_session: Session):
    row = fixture_suggestion()
    run = ReplenishmentRun(
        id=row.model_run_id, sku=row.sku, warehouse=row.warehouse,
        source=row.source, model_version=row.model_version, trained_at=row.trained_at,
        config_sha256="a" * 64, checkpoint_path="/example/checkpoint.pt", configuration={}, evaluation={},
    )
    original = publish(db_session, run, row, "b" * 64)
    state_key = row.sku, row.warehouse
    with Session(db_session.get_bind()) as reader:
        assert reader.get(ReplenishmentState, state_key) is None
        db_session.commit()
        state = reader.get(ReplenishmentState, state_key)
        assert state.snapshot_id == original.id
        assert reader.get(ReplenishmentSnapshot, state.snapshot_id).payload == row.model_dump(mode="json")

    updated = row.model_copy(update={"recommended_quantity": Decimal("20.000")})
    publish(db_session, run, updated, "c" * 64)
    db_session.rollback()
    record_status(db_session, row.sku, row.warehouse, "failed", "worker_failed")
    db_session.commit()

    with Session(db_session.get_bind()) as reader:
        state = reader.get(ReplenishmentState, state_key)
        assert state.status == "failed"
        assert state.snapshot_id == original.id
        assert reader.get(ReplenishmentSnapshot, state.snapshot_id).payload == row.model_dump(mode="json")
