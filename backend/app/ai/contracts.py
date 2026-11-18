"""Contrato de integração entre o sistema de estoque e modelos futuros de IA."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class ForecastInput:
    """Entrada padronizada fornecida ao motor de previsão e recomendação."""

    product_id: int
    sku: str
    product_name: str
    unit: str
    as_of_date: date
    horizon_days: int
    current_stock: Decimal
    safety_stock: Decimal
    lead_time_days: int
    lead_time_source: str
    open_purchase_orders_qty: Decimal
    history_df: pd.DataFrame


@dataclass(frozen=True)
class ForecastOutput:
    """Saída padronizada retornada por um provedor de previsão/recomendação."""

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


class DemandForecastProvider(Protocol):
    """Interface simples para acoplar futuros modelos Python (API ou lote)."""

    model_version: str
    is_connected: bool

    def predict(self, items: list[ForecastInput]) -> list[ForecastOutput]:
        """Gera previsões e recomendações de compra para cada produto informado."""
        ...
