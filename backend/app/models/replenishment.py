"""Persistent DQN runs, immutable suggestions and current eligibility state."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReplenishmentRun(Base):
    __tablename__ = "replenishment_runs"
    __table_args__ = (
        CheckConstraint("source IN ('synthetic', 'legacy_calibrated', 'operational_calibrated')", name="ck_replenishment_run_source"),
        Index("ix_replenishment_run_scope_config", "sku", "warehouse", "config_sha256", "trained_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sku: Mapped[str] = mapped_column(String(64))
    warehouse: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(24))
    model_version: Mapped[str] = mapped_column(String(64))
    config_sha256: Mapped[str] = mapped_column(String(64))
    checkpoint_path: Mapped[str] = mapped_column(String(1024))
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    configuration: Mapped[dict] = mapped_column(JSONB)
    evaluation: Mapped[dict] = mapped_column(JSONB)


class ReplenishmentSnapshot(Base):
    __tablename__ = "replenishment_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("replenishment_runs.id"), index=True)
    input_sha256: Mapped[str] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB)


class ReplenishmentState(Base):
    __tablename__ = "replenishment_states"
    __table_args__ = (
        CheckConstraint(
            "status IN ('calculating', 'insufficient_data', 'ready', 'failed')",
            name="ck_replenishment_state_status",
        ),
    )

    sku: Mapped[str] = mapped_column(String(64), primary_key=True)
    warehouse: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str | None] = mapped_column(String(256))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("replenishment_snapshots.id"))
