"""Esquema inicial do sistema de gestão de estoque e preparação para IA.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="OPERATOR"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("role IN ('ADMIN', 'OPERATOR')", name="ck_users_role"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "revoked_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("jti", name="uq_revoked_tokens_jti"),
    )
    op.create_index("ix_revoked_tokens_jti", "revoked_tokens", ["jti"], unique=True)

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("name", name="uq_categories_name"),
    )

    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("document", sa.String(length=32), nullable=True),
        sa.Column("contact_name", sa.String(length=120), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("default_lead_time_days", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "default_lead_time_days IS NULL OR default_lead_time_days >= 0",
            name="ck_suppliers_lead_time_non_negative",
        ),
    )
    op.create_index("ix_suppliers_name", "suppliers", ["name"])
    op.create_index(
        "uq_suppliers_document_not_null",
        "suppliers",
        ["document"],
        unique=True,
        postgresql_where=sa.text("document IS NOT NULL"),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("barcode", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False, server_default="0.00"),
        sa.Column("min_stock", sa.Numeric(14, 3), nullable=False, server_default="0.000"),
        sa.Column("safety_stock", sa.Numeric(14, 3), nullable=False, server_default="0.000"),
        sa.Column("current_stock", sa.Numeric(14, 3), nullable=False, server_default="0.000"),
        sa.Column("location", sa.String(length=120), nullable=True),
        sa.Column(
            "preferred_supplier_id",
            sa.Integer(),
            sa.ForeignKey("suppliers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("unit_cost >= 0", name="ck_products_unit_cost_non_negative"),
        sa.CheckConstraint("min_stock >= 0", name="ck_products_min_stock_non_negative"),
        sa.CheckConstraint("safety_stock >= 0", name="ck_products_safety_stock_non_negative"),
        sa.CheckConstraint("current_stock >= 0", name="ck_products_current_stock_non_negative"),
        sa.CheckConstraint(
            "lead_time_days IS NULL OR lead_time_days >= 0",
            name="ck_products_lead_time_non_negative",
        ),
        sa.UniqueConstraint("sku", name="uq_products_sku"),
    )
    op.create_index("ix_products_name", "products", ["name"])
    op.create_index("ix_products_sku", "products", ["sku"], unique=True)
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_index(
        "uq_products_barcode_not_null",
        "products",
        ["barcode"],
        unique=True,
        postgresql_where=sa.text("barcode IS NOT NULL"),
    )

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("movement_type", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=30), nullable=False),
        sa.Column("is_demand", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("signed_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_snapshot", sa.String(length=16), nullable=False),
        sa.Column("balance_before", sa.Numeric(14, 3), nullable=False),
        sa.Column("balance_after", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "supplier_id",
            sa.Integer(),
            sa.ForeignKey("suppliers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("order_date", sa.Date(), nullable=True),
        sa.Column("received_date", sa.Date(), nullable=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "reference_movement_id",
            sa.Integer(),
            sa.ForeignKey("stock_movements.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "movement_type IN ('ENTRADA', 'SAIDA', 'AJUSTE', 'ESTORNO')",
            name="ck_stock_movements_type",
        ),
        sa.CheckConstraint(
            "reason_code IN ('RECEBIMENTO', 'SALDO_INICIAL', 'VENDA', 'CONSUMO', 'PERDA', 'AVARIA', 'OUTRO', 'AJUSTE_POSITIVO', 'AJUSTE_NEGATIVO', 'ESTORNO')",
            name="ck_stock_movements_reason",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_stock_movements_quantity_positive"),
        sa.CheckConstraint("signed_quantity <> 0", name="ck_stock_movements_signed_nonzero"),
        sa.CheckConstraint("balance_before >= 0", name="ck_stock_movements_balance_before_non_neg"),
        sa.CheckConstraint("balance_after >= 0", name="ck_stock_movements_balance_after_non_neg"),
        sa.CheckConstraint(
            "unit_cost IS NULL OR unit_cost >= 0",
            name="ck_stock_movements_unit_cost_non_neg",
        ),
    )
    op.create_index("ix_stock_movements_product_id", "stock_movements", ["product_id"])
    op.create_index("ix_stock_movements_movement_type", "stock_movements", ["movement_type"])
    op.create_index("ix_stock_movements_reason_code", "stock_movements", ["reason_code"])
    op.create_index("ix_stock_movements_user_id", "stock_movements", ["user_id"])
    op.create_index("ix_stock_movements_created_at", "stock_movements", ["created_at"])
    op.create_index(
        "uq_stock_movements_reference_not_null",
        "stock_movements",
        ["reference_movement_id"],
        unique=True,
        postgresql_where=sa.text("reference_movement_id IS NOT NULL"),
    )

    op.create_table(
        "stockout_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "start_movement_id",
            sa.Integer(),
            sa.ForeignKey("stock_movements.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "end_movement_id",
            sa.Integer(),
            sa.ForeignKey("stock_movements.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_stockout_periods_product_id", "stockout_periods", ["product_id"])

    op.create_table(
        "historical_import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PREVIEW"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("preview_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column(
            "uploaded_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('PREVIEW', 'CONFIRMED')", name="ck_import_batch_status"),
    )
    op.create_index(
        "ix_historical_import_batches_file_sha256",
        "historical_import_batches",
        ["file_sha256"],
    )

    op.create_table(
        "historical_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("historical_import_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_row_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("movement_type", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=30), nullable=False),
        sa.Column("is_demand", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_snapshot", sa.String(length=16), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("supplier_name", sa.String(length=150), nullable=True),
        sa.Column("order_date", sa.Date(), nullable=True),
        sa.Column("received_date", sa.Date(), nullable=True),
        sa.Column("closing_stock_reported", sa.Numeric(14, 3), nullable=True),
        sa.Column("had_stockout", sa.Boolean(), nullable=True),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("quantity > 0", name="ck_historical_movements_qty_positive"),
        sa.UniqueConstraint("external_row_hash", name="uq_historical_movements_row_hash"),
    )
    op.create_index("ix_historical_movements_batch_id", "historical_movements", ["batch_id"])
    op.create_index(
        "ix_historical_movements_external_row_hash",
        "historical_movements",
        ["external_row_hash"],
        unique=True,
    )
    op.create_index("ix_historical_movements_product_id", "historical_movements", ["product_id"])
    op.create_index("ix_historical_movements_occurred_at", "historical_movements", ["occurred_at"])


def downgrade() -> None:
    op.drop_table("historical_movements")
    op.drop_table("historical_import_batches")
    op.drop_table("stockout_periods")
    op.drop_table("stock_movements")
    op.drop_table("products")
    op.drop_table("suppliers")
    op.drop_table("categories")
    op.drop_table("revoked_tokens")
    op.drop_table("users")
