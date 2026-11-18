"""Modelos ORM para movimentações imutáveis e períodos de ruptura de estoque."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class StockMovement(Base):
    """Registro imutável de entrada, saída, ajuste ou estorno de estoque."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint(
            "movement_type IN ('ENTRADA', 'SAIDA', 'AJUSTE', 'ESTORNO')",
            name="ck_stock_movements_type",
        ),
        CheckConstraint(
            "reason_code IN ('RECEBIMENTO', 'SALDO_INICIAL', 'VENDA', 'CONSUMO', 'PERDA', 'AVARIA', 'OUTRO', 'AJUSTE_POSITIVO', 'AJUSTE_NEGATIVO', 'ESTORNO')",
            name="ck_stock_movements_reason",
        ),
        CheckConstraint("quantity > 0", name="ck_stock_movements_quantity_positive"),
        CheckConstraint("signed_quantity <> 0", name="ck_stock_movements_signed_nonzero"),
        CheckConstraint("balance_before >= 0", name="ck_stock_movements_balance_before_non_neg"),
        CheckConstraint("balance_after >= 0", name="ck_stock_movements_balance_after_non_neg"),
        CheckConstraint(
            "unit_cost IS NULL OR unit_cost >= 0",
            name="ck_stock_movements_unit_cost_non_neg",
        ),
        Index(
            "uq_stock_movements_reference_not_null",
            "reference_movement_id",
            unique=True,
            postgresql_where=text("reference_movement_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    movement_type: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    is_demand: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    signed_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_snapshot: Mapped[str] = mapped_column(String(16), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    reference_movement_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_movements.id", ondelete="RESTRICT"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False, server_default=func.now()
    )

    product = relationship("Product")
    supplier = relationship("Supplier")
    user = relationship("User")
    reference_movement = relationship("StockMovement", remote_side=[id], uselist=False)


class StockoutPeriod(Base):
    """Período contínuo em que o produto esteve com saldo igual a zero (ruptura)."""

    __tablename__ = "stockout_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    start_movement_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_movements.id", ondelete="SET NULL"), nullable=True
    )
    end_movement_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_movements.id", ondelete="SET NULL"), nullable=True
    )
