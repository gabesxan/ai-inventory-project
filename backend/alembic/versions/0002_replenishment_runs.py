"""Persist trained runs and atomically published replenishment snapshots."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0002_replenishment_runs"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "replenishment_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("warehouse", sa.String(64), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("config_sha256", sa.String(64), nullable=False),
        sa.Column("checkpoint_path", sa.String(1024), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("configuration", JSONB, nullable=False),
        sa.Column("evaluation", JSONB, nullable=False),
        sa.CheckConstraint("source IN ('synthetic', 'legacy_calibrated')", name="ck_replenishment_run_source"),
    )
    op.create_index(
        "ix_replenishment_run_scope_config", "replenishment_runs",
        ["sku", "warehouse", "config_sha256", "trained_at"],
    )
    op.create_table(
        "replenishment_snapshots",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("replenishment_runs.id"), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
    )
    op.create_index("ix_replenishment_snapshots_run_id", "replenishment_snapshots", ["run_id"])
    op.create_table(
        "replenishment_states",
        sa.Column("sku", sa.String(64), primary_key=True),
        sa.Column("warehouse", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(256), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_id", sa.BigInteger, sa.ForeignKey("replenishment_snapshots.id"), nullable=True),
        sa.CheckConstraint(
            "status IN ('calculating', 'insufficient_data', 'ready', 'failed')",
            name="ck_replenishment_state_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("replenishment_states")
    op.drop_index("ix_replenishment_snapshots_run_id", table_name="replenishment_snapshots")
    op.drop_table("replenishment_snapshots")
    op.drop_index("ix_replenishment_run_scope_config", table_name="replenishment_runs")
    op.drop_table("replenishment_runs")
