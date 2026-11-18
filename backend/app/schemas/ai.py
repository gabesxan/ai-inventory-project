"""Schemas do módulo de preparação de dados e contrato de previsão de IA."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class ImportRowErrorOut(BaseModel):
    """Erro detalhado por linha na prévia de importação CSV."""

    line_number: int
    sku: str | None
    message: str


class ImportValidRowPreview(BaseModel):
    """Amostra de linha válida na prévia antes da confirmação."""

    line_number: int
    sku: str
    product_name: str
    occurred_at: datetime
    movement_type: str
    reason_code: str
    quantity: Decimal
    unit_snapshot: str
    unit_cost: Decimal | None
    is_demand: bool
    is_synthetic: bool


class ImportPreviewOut(BaseModel):
    """Resultado da análise prévia de um CSV histórico."""

    batch_id: int
    filename: str
    file_sha256: str
    file_already_imported: bool
    status: str
    total_rows: int
    valid_rows: int
    error_rows: int
    duplicate_rows: int
    is_synthetic: bool
    errors: list[ImportRowErrorOut]
    sample_valid_rows: list[ImportValidRowPreview]
    notice: str


class ImportConfirmOut(BaseModel):
    """Resultado da confirmação da importação histórica para estudo."""

    batch_id: int
    status: str
    inserted_rows: int
    confirmed_at: datetime
    notice: str


class ImportBatchSummaryOut(BaseModel):
    """Histórico resumido dos lotes importados."""

    id: int
    filename: str
    status: str
    total_rows: int
    valid_rows: int
    error_rows: int
    duplicate_rows: int
    is_synthetic: bool
    created_at: datetime
    confirmed_at: datetime | None


class DataReadinessSummary(BaseModel):
    """Resumo da base histórica disponível para futuros modelos de IA."""

    active_products: int
    operational_movements: int
    operational_demand_events: int
    historical_study_movements: int
    stockout_periods_recorded: int


class PurchaseSuggestionItemOut(BaseModel):
    """Sugestão de compra gerada para apoio à decisão humana."""

    product_id: int
    sku: str
    product_name: str
    unit: str
    available_stock: Decimal
    safety_stock: Decimal
    open_purchase_orders_qty: Decimal
    lead_time_days: int
    lead_time_source: str
    horizon_days: int
    effective_coverage_days: int
    predicted_demand_horizon: Decimal
    predicted_demand_effective_window: Decimal
    recommended_purchase_qty: Decimal
    prediction_interval_low: Decimal | None
    prediction_interval_high: Decimal | None
    model_version: str
    generated_at: datetime
    period_start: date
    period_end: date
    reason_summary: str
    is_simulated: bool
    history_days_used: int


class PurchaseSuggestionsResponse(BaseModel):
    """Resposta do módulo de sugestões de compra (com ou sem modelo conectado)."""

    model_connected: bool
    is_simulated: bool
    model_version: str | None
    status_title: str
    status_message: str
    replenishment_rule_note: str
    human_decision_notice: str
    horizon_days: int
    data_readiness: DataReadinessSummary
    items: list[PurchaseSuggestionItemOut]
