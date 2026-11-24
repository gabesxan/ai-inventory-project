"""Database operations shared by the replenishment worker and reports."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.replenishment import ReplenishmentRun, ReplenishmentSnapshot, ReplenishmentState
from app.schemas.reports import ReplenishmentRow


def record_status(
    db: Session, sku: str, warehouse: str, status: str, reason: str | None = None
) -> ReplenishmentState:
    state = db.get(ReplenishmentState, (sku, warehouse))
    if state is None:
        state = ReplenishmentState(sku=sku, warehouse=warehouse)
        db.add(state)
    state.status = status
    state.reason = reason
    state.updated_at = datetime.now(timezone.utc)
    return state


def publish(
    db: Session, run: ReplenishmentRun, row: ReplenishmentRow, input_sha256: str
) -> ReplenishmentSnapshot:
    if (row.model_run_id, row.sku, row.warehouse, row.source, row.model_version) != (
        run.id, run.sku, run.warehouse, run.source, run.model_version,
    ):
        raise ValueError("Suggestion does not match the model run")
    db.add(run)
    db.flush()
    snapshot = ReplenishmentSnapshot(
        run_id=run.id,
        input_sha256=input_sha256,
        generated_at=row.generated_at,
        payload=row.model_dump(mode="json"),
    )
    db.add(snapshot)
    db.flush()
    state = record_status(db, row.sku, row.warehouse, "ready")
    state.snapshot_id = snapshot.id
    return snapshot
