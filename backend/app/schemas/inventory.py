"""Schemas para movimentações operacionais de estoque."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


EntryReason = Literal["RECEBIMENTO", "SALDO_INICIAL"]
ExitReason = Literal["VENDA", "CONSUMO", "PERDA", "AVARIA", "OUTRO"]
AdjustmentDirection = Literal["POSITIVO", "NEGATIVO"]


class EntryMovementCreate(BaseModel):
    """Entrada de estoque por recebimento ou saldo inicial."""

    product_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=Decimal("0"))
    reason_code: EntryReason = "RECEBIMENTO"
    unit_cost: Decimal | None = Field(default=None, ge=Decimal("0"))
    supplier_id: int | None = Field(default=None, gt=0)
    order_date: date | None = None
    received_date: date | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class ExitMovementCreate(BaseModel):
    """Saída de estoque com classificação padronizada para IA."""

    product_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=Decimal("0"))
    reason_code: ExitReason
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class AdjustmentMovementCreate(BaseModel):
    """Ajuste positivo ou negativo permitido apenas a Administradores."""

    product_id: int = Field(gt=0)
    direction: AdjustmentDirection
    quantity: Decimal = Field(gt=Decimal("0"))
    notes: str = Field(min_length=5, max_length=1000)

    @field_validator("notes")
    @classmethod
    def validate_justification(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 5:
            raise ValueError("A justificativa do ajuste deve ter ao menos 5 caracteres.")
        return cleaned


class ReversalCreate(BaseModel):
    """Solicitação de estorno de movimentação por Administrador."""

    notes: str = Field(min_length=5, max_length=1000)

    @field_validator("notes")
    @classmethod
    def validate_justification(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 5:
            raise ValueError("A justificativa do estorno deve ter ao menos 5 caracteres.")
        return cleaned


class MovementOut(BaseModel):
    """Representação completa de uma movimentação imutável."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str
    product_sku: str
    product_unit: str
    movement_type: str
    reason_code: str
    is_demand: bool
    quantity: Decimal
    signed_quantity: Decimal
    unit_snapshot: str
    balance_before: Decimal
    balance_after: Decimal
    unit_cost: Decimal | None
    supplier_id: int | None
    supplier_name: str | None
    order_date: date | None
    received_date: date | None
    actual_lead_time_days: int | None
    user_id: int
    user_name: str
    reference_movement_id: int | None
    reversed_by_movement_id: int | None
    notes: str | None
    is_synthetic: bool
    created_at: datetime


class MovementResponsibleOut(BaseModel):
    """Resumo de usuário para filtro por responsável no histórico."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
