"""Modelos ORM para importação histórica de dados analíticos para IA."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class HistoricalImportBatch(Base):
    """Lote de importação CSV de séries históricas (não altera saldo operacional)."""

    __tablename__ = "historical_import_batches"
    __table_args__ = (
        CheckConstraint("status IN ('PREVIEW', 'CONFIRMED')", name="ck_import_batch_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PREVIEW")
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    preview_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    uploaded_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    uploaded_by = relationship("User")


class HistoricalMovement(Base):
    """Registro histórico importado exclusivamente para estudo e modelagem de IA."""

    __tablename__ = "historical_movements"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_historical_movements_qty_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("historical_import_batches.id", ondelete="CASCADE"), index=True, nullable=False
    )
    external_row_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(30), nullable=False)
    is_demand: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_snapshot: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closing_stock_reported: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    had_stockout: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    batch = relationship("HistoricalImportBatch")
    product = relationship("Product")
