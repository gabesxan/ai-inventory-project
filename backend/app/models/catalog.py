"""Modelos ORM para categorias, fornecedores e produtos."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class Category(Base):
    """Categoria de agrupamento de produtos."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Supplier(Base):
    """Fornecedor de mercadorias."""

    __tablename__ = "suppliers"
    __table_args__ = (
        CheckConstraint(
            "default_lead_time_days IS NULL OR default_lead_time_days >= 0",
            name="ck_suppliers_lead_time_non_negative",
        ),
        Index(
            "uq_suppliers_document_not_null",
            "document",
            unique=True,
            postgresql_where=text("document IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    document: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    default_lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Product(Base):
    """Produto gerenciado no estoque único da empresa."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("unit_cost >= 0", name="ck_products_unit_cost_non_negative"),
        CheckConstraint("min_stock >= 0", name="ck_products_min_stock_non_negative"),
        CheckConstraint("safety_stock >= 0", name="ck_products_safety_stock_non_negative"),
        CheckConstraint("current_stock >= 0", name="ck_products_current_stock_non_negative"),
        CheckConstraint(
            "lead_time_days IS NULL OR lead_time_days >= 0",
            name="ck_products_lead_time_non_negative",
        ),
        Index(
            "uq_products_barcode_not_null",
            "barcode",
            unique=True,
            postgresql_where=text("barcode IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    min_stock: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0.000")
    )
    safety_stock: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0.000")
    )
    current_stock: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0.000")
    )
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    preferred_supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    category: Mapped[Category] = relationship(back_populates="products")
    preferred_supplier: Mapped[Supplier | None] = relationship()
