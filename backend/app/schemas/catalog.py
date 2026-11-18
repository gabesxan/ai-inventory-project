"""Schemas de categorias, fornecedores e produtos."""

from datetime import datetime
from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import EmailValue
from app.services.units import normalize_unit, quantize_money


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Envelope padrão de resposta paginada."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class CategoryCreate(BaseModel):
    """Dados para criação ou edição de categoria."""

    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("O nome da categoria deve ter ao menos 2 caracteres.")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None


class CategoryOut(BaseModel):
    """Saída de categoria."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SupplierCreate(BaseModel):
    """Dados para criação ou edição de fornecedor."""

    name: str = Field(min_length=2, max_length=150)
    document: str | None = Field(default=None, max_length=32)
    contact_name: str | None = Field(default=None, max_length=120)
    email: EmailValue | None = None
    phone: str | None = Field(default=None, max_length=40)
    default_lead_time_days: int | None = Field(default=None, ge=0, le=3650)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("O nome do fornecedor deve ter ao menos 2 caracteres.")
        return cleaned

    @field_validator("document", "contact_name", "phone", "notes")
    @classmethod
    def empty_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None

    @field_validator("email", mode="before")
    @classmethod
    def empty_email_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v


class SupplierOut(BaseModel):
    """Saída de fornecedor."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    document: str | None
    contact_name: str | None
    email: str | None
    phone: str | None
    default_lead_time_days: int | None
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProductCreate(BaseModel):
    """Dados para criação ou edição cadastral de produto (saldo inicial sempre zero)."""

    name: str = Field(min_length=2, max_length=180)
    sku: str = Field(min_length=2, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=1000)
    category_id: int = Field(gt=0)
    unit: str = Field(min_length=1, max_length=16)
    unit_cost: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    min_stock: Decimal = Field(default=Decimal("0.000"), ge=Decimal("0"))
    safety_stock: Decimal = Field(default=Decimal("0.000"), ge=Decimal("0"))
    location: str | None = Field(default=None, max_length=120)
    preferred_supplier_id: int | None = Field(default=None, gt=0)
    lead_time_days: int | None = Field(default=None, ge=0, le=3650)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("O nome do produto deve ter ao menos 2 caracteres.")
        return cleaned

    @field_validator("sku")
    @classmethod
    def clean_sku(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if len(cleaned) < 2 or " " in cleaned:
            raise ValueError("O SKU deve ter ao menos 2 caracteres e não conter espaços.")
        return cleaned

    @field_validator("barcode", "description", "location")
    @classmethod
    def empty_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None

    @field_validator("unit")
    @classmethod
    def check_unit(cls, v: str) -> str:
        return normalize_unit(v)

    @field_validator("unit_cost")
    @classmethod
    def round_cost(cls, v: Decimal) -> Decimal:
        return quantize_money(v)


class ProductOut(BaseModel):
    """Saída detalhada de produto."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sku: str
    barcode: str | None
    description: str | None
    category_id: int
    category_name: str
    unit: str
    unit_label: str
    is_discrete_unit: bool
    unit_cost: Decimal
    min_stock: Decimal
    safety_stock: Decimal
    current_stock: Decimal
    estimated_total_value: Decimal
    location: str | None
    preferred_supplier_id: int | None
    preferred_supplier_name: str | None
    lead_time_days: int | None
    is_active: bool
    has_movements: bool
    stock_status: str
    created_at: datetime
    updated_at: datetime


class UnitSpecOut(BaseModel):
    """Descrição de unidade suportada para uso na interface."""

    code: str
    label: str
    allow_decimal: bool
