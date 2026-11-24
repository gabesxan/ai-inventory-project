"""Version 1 wire contracts for inventory reports and legacy import evidence."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, Field

from app.schemas.catalog import PaginatedResponse


ReportStatus = Literal["ready", "calculating", "insufficient_data", "stale", "empty"]
ModelSource = Literal["synthetic", "legacy_calibrated"]
Coverage = Literal["available", "stockout", "unknown", "uncovered"]
Quantity = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)]
Count = Annotated[int, Field(ge=0)]
T = TypeVar("T")


class VersionedReport(PaginatedResponse[T], Generic[T]):
    schema_version: Literal[1] = 1
    status: ReportStatus
    status_message: str | None


class ModelProvenance(BaseModel):
    model_run_id: str
    model_version: str
    scenario: str
    source: ModelSource
    reference_date: date
    trained_at: AwareDatetime
    generated_at: AwareDatetime


class ReplenishmentRow(ModelProvenance):
    sku: str
    product_name: str
    warehouse: str
    recommended_quantity: Quantity
    unit: str
    policy: Literal["dqn"] = "dqn"


class ComparisonRow(ModelProvenance):
    policy: Literal["dqn", "base_stock", "s_s"]
    seed: int
    total_cost: Decimal | None
    fill_rate: Annotated[Decimal, Field(ge=0, le=1)] | None
    stockout_days: Count | None
    mean_inventory: Decimal | None
    order_days: Count | None


class ImportedHistoryRow(BaseModel):
    record_id: str
    sku: str
    product_name: str
    warehouse: str
    event_date: date
    event_type: str
    quantity: Quantity
    unit: str
    unit_cost: Decimal | None
    stock_availability: Coverage
    source: Literal["firebird"] = "firebird"
    batch_id: str
    source_date: date | None


class InventoryExceptionRow(BaseModel):
    sku: str
    warehouse: str
    reference_date: date
    coverage: Literal["stockout", "unknown", "uncovered"]
    reason: str
    source: Literal["firebird"] = "firebird"
    batch_id: str
    source_date: date | None


class CoverageCounts(BaseModel):
    available_days: Count
    stockout_days: Count
    unknown_days: Count
    uncovered_days: Count


class ImportQualityRow(BaseModel):
    batch_id: str
    source: Literal["firebird"] = "firebird"
    warehouse: str
    source_date: date | None
    period_start: date | None
    period_end: date | None
    status: Literal["imported", "failed"]
    imported_at: AwareDatetime | None
    accepted_rows: Count
    rejected_rows: Count
    duplicate_rows: Count
    rejection_reasons: dict[str, Count]
    coverage: CoverageCounts | None


class LegacyPreviewDiagnostic(BaseModel):
    dataset: str
    line_number: Annotated[int, Field(ge=1)] | None
    reason: str


class LegacyImportPreview(BaseModel):
    schema_version: Literal[1] = 1
    status: Literal["ready", "invalid"]
    source: Literal["firebird"] = "firebird"
    warehouse: str
    source_date: date | None
    total_rows: Count
    valid_rows: Count
    rejected_rows: Count
    duplicate_rows: Count
    diagnostics: list[LegacyPreviewDiagnostic]


class ReportError(BaseModel):
    detail: str
