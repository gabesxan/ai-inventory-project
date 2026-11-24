"""Staging aditivo para a importação do banco legado Firebird (DB-13).

Revision ID: 0002_legacy_staging
Revises: 0001_initial_schema
Create Date: 2026-11-24

Somente tabelas novas ``legacy_*``: nenhuma tabela da v1 é alterada. O saldo operacional
(``products.current_stock`` e ``stock_movements``) só muda por uma confirmação explícita.
As tabelas de abertura (DB-10) e de vínculos de catálogo (DB-06) deixam de ser criadas
pelos importadores e passam a viver aqui.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002_legacy_staging"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AVAILABILITY = ("available", "stockout", "unknown", "uncovered")
EVENT_CLASSES = ("sale", "receipt", "return", "other_outbound")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.create_table(
        "legacy_import_batches",
        sa.Column("batch_id", sa.String(64), primary_key=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="firebird"),
        sa.Column("source_system", sa.String(60), nullable=False),
        sa.Column("warehouse_key", sa.String(120), nullable=False),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("accepted_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejection_reasons", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("coverage", postgresql.JSONB(), nullable=True),
        sa.Column("failure_reason", sa.String(80), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("source = 'firebird'", name="ck_legacy_batches_source"),
        sa.CheckConstraint("status IN ('imported', 'failed')", name="ck_legacy_batches_status"),
        sa.CheckConstraint(
            "accepted_rows >= 0 AND rejected_rows >= 0 AND duplicate_rows >= 0",
            name="ck_legacy_batches_counts_non_neg",
        ),
        sa.CheckConstraint(
            "period_end IS NULL OR period_start IS NULL OR period_end >= period_start",
            name="ck_legacy_batches_period",
        ),
        sa.UniqueConstraint("warehouse_key", "source_fingerprint", name="uq_legacy_batches_scope_fingerprint"),
    )
    op.create_index("ix_legacy_import_batches_imported_at", "legacy_import_batches", ["imported_at"])

    op.create_table(
        "legacy_history_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("batch_id", sa.String(64), sa.ForeignKey("legacy_import_batches.batch_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("record_id", sa.String(200), nullable=False),
        sa.Column("warehouse_key", sa.String(120), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("event_class", sa.String(20), nullable=False),
        sa.Column("is_demand", sa.Boolean(), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("signed_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 6), nullable=True),
        sa.Column("stock_availability", sa.String(12), nullable=False, server_default="unknown"),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(_in("event_class", EVENT_CLASSES), name="ck_legacy_history_event_class"),
        sa.CheckConstraint(_in("stock_availability", AVAILABILITY), name="ck_legacy_history_availability"),
        sa.CheckConstraint("quantity >= 0", name="ck_legacy_history_quantity_non_neg"),
        sa.CheckConstraint("quantity = abs(signed_quantity)", name="ck_legacy_history_signed_matches"),
        sa.CheckConstraint("unit_cost IS NULL OR unit_cost >= 0", name="ck_legacy_history_unit_cost_non_neg"),
        sa.UniqueConstraint("warehouse_key", "record_id", name="uq_legacy_history_scope_record"),
    )
    op.create_index("ix_legacy_history_events_batch_id", "legacy_history_events", ["batch_id"])
    op.create_index("ix_legacy_history_events_product_date", "legacy_history_events", ["product_id", "event_date"])
    op.create_index("ix_legacy_history_events_date", "legacy_history_events", ["event_date"])

    op.create_table(
        "legacy_coverage_series",
        sa.Column("warehouse_key", sa.String(120), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("batch_id", sa.String(64), sa.ForeignKey("legacy_import_batches.batch_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("source", sa.String(300), nullable=False),
        sa.Column("availability_basis", sa.String(200), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("sale_days", sa.Integer(), nullable=False),
        sa.Column("true_zero_days", sa.Integer(), nullable=False),
        sa.Column("zero_unknown_availability_days", sa.Integer(), nullable=False),
        sa.Column("known_stockout_days", sa.Integer(), nullable=False),
        sa.Column("unknown_quantity_days", sa.Integer(), nullable=False),
        sa.Column("calendar_gap_days", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("warehouse_key", "product_id", name="pk_legacy_coverage_series"),
        sa.CheckConstraint(
            "days >= 0 AND sale_days >= 0 AND true_zero_days >= 0 AND zero_unknown_availability_days >= 0 "
            "AND known_stockout_days >= 0 AND unknown_quantity_days >= 0 AND calendar_gap_days >= 0",
            name="ck_legacy_coverage_non_neg",
        ),
        sa.CheckConstraint(
            "days = sale_days + true_zero_days + zero_unknown_availability_days + known_stockout_days "
            "+ unknown_quantity_days + calendar_gap_days",
            name="ck_legacy_coverage_days_add_up",
        ),
        sa.CheckConstraint("period_end >= period_start", name="ck_legacy_coverage_period"),
    )
    op.create_index("ix_legacy_coverage_series_batch_id", "legacy_coverage_series", ["batch_id"])

    # Day-level DB-12 evidence as runs of consecutive days with one status (5.26M real product-days
    # are 409,640 runs). ``coverage`` is the API-01 vocabulary and ``uncensored`` marks days usable for
    # demand calibration; both are derived here so the mapping cannot drift between loaders.
    op.create_table(
        "legacy_coverage_ranges",
        sa.Column("warehouse_key", sa.String(120), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("day_status", sa.String(32), nullable=False),
        sa.Column("batch_id", sa.String(64), sa.ForeignKey("legacy_import_batches.batch_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("coverage", sa.String(12), sa.Computed(
            "CASE day_status WHEN 'sale' THEN 'available' WHEN 'true_zero' THEN 'available' "
            "WHEN 'known_stockout' THEN 'stockout' WHEN 'calendar_gap' THEN 'uncovered' ELSE 'unknown' END",
            persisted=True)),
        sa.Column("uncensored", sa.Boolean(), sa.Computed("day_status IN ('sale', 'true_zero')", persisted=True)),
        sa.PrimaryKeyConstraint("warehouse_key", "product_id", "start_date", name="pk_legacy_coverage_ranges"),
        sa.CheckConstraint(
            "day_status IN ('sale', 'true_zero', 'zero_unknown_availability', 'known_stockout', "
            "'unknown_quantity', 'calendar_gap')", name="ck_legacy_ranges_day_status"),
        sa.CheckConstraint("end_date >= start_date", name="ck_legacy_ranges_period"),
    )
    op.create_index("ix_legacy_coverage_ranges_batch_id", "legacy_coverage_ranges", ["batch_id"])
    op.create_index("ix_legacy_coverage_ranges_coverage", "legacy_coverage_ranges", ["warehouse_key", "coverage", "start_date"])

    op.create_table(
        "legacy_import_rejections",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("batch_id", sa.String(64), sa.ForeignKey("legacy_import_batches.batch_id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset", sa.String(60), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.Column("record_key", sa.String(200), nullable=True),
        sa.CheckConstraint("line_number IS NULL OR line_number >= 1", name="ck_legacy_rejections_line"),
    )
    op.create_index("ix_legacy_import_rejections_batch_reason", "legacy_import_rejections", ["batch_id", "reason"])

    # DB-10: abertura de estoque datada (hoje sem linhas: decisão "sem estoque de abertura").
    op.create_table(
        "legacy_opening_snapshots",
        sa.Column("snapshot_id", sa.String(32), primary_key=True),
        sa.Column("source_date", sa.Date(), nullable=False),
        sa.Column("warehouse_key", sa.String(120), nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "legacy_opening_entries",
        sa.Column("product_key", sa.String(120), primary_key=True),
        sa.Column("snapshot_id", sa.String(32), sa.ForeignKey("legacy_opening_snapshots.snapshot_id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("qty", sa.Numeric(14, 3), nullable=False),
        sa.Column("source_date", sa.Date(), nullable=False),
        sa.Column("movement_id", sa.Integer(), sa.ForeignKey("stock_movements.id"), nullable=True),
        sa.CheckConstraint("qty >= 0", name="ck_legacy_opening_entries_qty_non_neg"),
    )

    # DB-06: origem estável, vínculos produto-fornecedor e vínculos não resolvidos.
    op.create_table(
        "legacy_origin",
        sa.Column("entity", sa.String(20), nullable=False),
        sa.Column("origin_key", sa.String(120), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("entity", "origin_key"),
    )
    op.create_table(
        "legacy_product_suppliers",
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.PrimaryKeyConstraint("product_id", "supplier_id", "source"),
    )
    op.create_table(
        "legacy_unresolved_links",
        sa.Column("product_key", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("product_key", "kind", "detail"),
    )


def downgrade() -> None:
    for table in (
        "legacy_unresolved_links",
        "legacy_product_suppliers",
        "legacy_origin",
        "legacy_opening_entries",
        "legacy_opening_snapshots",
        "legacy_import_rejections",
        "legacy_coverage_ranges",
        "legacy_coverage_series",
        "legacy_history_events",
        "legacy_import_batches",
    ):
        op.drop_table(table)
