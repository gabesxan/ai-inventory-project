"""Schemas do painel (dashboard) e relatórios."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class UnitPeriodSummary(BaseModel):
    """Totais do período segregados por unidade de medida compatível."""

    unit: str
    unit_label: str
    entries_qty: Decimal
    exits_qty: Decimal
    demand_exits_qty: Decimal


class DailyUnitFlow(BaseModel):
    """Quantidades diárias para uma unidade específica."""

    entries_qty: Decimal
    exits_qty: Decimal


class DailyChartPoint(BaseModel):
    """Ponto diário de movimentações no período."""

    date: date
    label: str
    entries_count: int
    exits_count: int
    by_unit: dict[str, DailyUnitFlow]


class ReplenishmentAlertItem(BaseModel):
    """Item listado no alerta de reposição do painel."""

    product_id: int
    sku: str
    name: str
    category_name: str
    unit: str
    current_stock: Decimal
    min_stock: Decimal
    deficit: Decimal
    preferred_supplier_name: str | None
    lead_time_days: int | None
    stock_status: str


class DashboardOut(BaseModel):
    """Indicadores consolidados do painel com dados reais do banco."""

    active_products_count: int
    out_of_stock_count: int
    below_min_stock_count: int
    estimated_stock_value_brl: Decimal
    valuation_formula: str
    valuation_disclaimer: str
    period_start: date
    period_end: date
    entries_count: int
    exits_count: int
    adjustments_count: int
    reversals_count: int
    unit_summaries: list[UnitPeriodSummary]
    daily_chart: list[DailyChartPoint]
    replenishment_list: list[ReplenishmentAlertItem]
