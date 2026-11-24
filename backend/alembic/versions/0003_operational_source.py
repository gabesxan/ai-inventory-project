"""Allow the app stock ledger as a distinct source of model calibration."""

from alembic import op


revision = "0003_operational_source"
down_revision = "0002_replenishment_runs"
branch_labels = None
depends_on = None

TABLE = "replenishment_runs"
CONSTRAINT = "ck_replenishment_run_source"
LEGACY_SOURCES = "source IN ('synthetic', 'legacy_calibrated')"
EXPANDED_SOURCES = "source IN ('synthetic', 'legacy_calibrated', 'operational_calibrated')"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(CONSTRAINT, TABLE, EXPANDED_SOURCES)


def downgrade() -> None:
    # Restoring the old constraint deliberately fails while operational runs exist.
    op.drop_constraint(CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(CONSTRAINT, TABLE, LEGACY_SOURCES)
