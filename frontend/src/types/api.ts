export type UserRole = "ADMIN" | "OPERATOR";

export interface User {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface MovementResponsible {
  id: number;
  name: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: User;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface Category {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Supplier {
  id: number;
  name: string;
  document: string | null;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  default_lead_time_days: number | null;
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface UnitSpec {
  code: string;
  label: string;
  allow_decimal: boolean;
}

export interface Product {
  id: number;
  name: string;
  sku: string;
  barcode: string | null;
  description: string | null;
  category_id: number;
  category_name: string;
  unit: string;
  unit_label: string;
  is_discrete_unit: boolean;
  unit_cost: string;
  min_stock: string;
  safety_stock: string;
  current_stock: string;
  estimated_total_value: string;
  location: string | null;
  preferred_supplier_id: number | null;
  preferred_supplier_name: string | null;
  lead_time_days: number | null;
  is_active: boolean;
  has_movements: boolean;
  stock_status: "OK" | "BELOW_MIN" | "OUT_OF_STOCK";
  created_at: string;
  updated_at: string;
}

export interface StockMovement {
  id: number;
  product_id: number;
  product_name: string;
  product_sku: string;
  product_unit: string;
  movement_type: "ENTRADA" | "SAIDA" | "AJUSTE" | "ESTORNO";
  reason_code: string;
  is_demand: boolean;
  quantity: string;
  signed_quantity: string;
  unit_snapshot: string;
  balance_before: string;
  balance_after: string;
  unit_cost: string | null;
  supplier_id: number | null;
  supplier_name: string | null;
  order_date: string | null;
  received_date: string | null;
  actual_lead_time_days: number | null;
  user_id: number;
  user_name: string;
  reference_movement_id: number | null;
  reversed_by_movement_id: number | null;
  notes: string | null;
  is_synthetic: boolean;
  created_at: string;
}

export interface UnitPeriodSummary {
  unit: string;
  unit_label: string;
  entries_qty: string;
  exits_qty: string;
  demand_exits_qty: string;
}

export interface DailyChartPoint {
  date: string;
  label: string;
  entries_count: number;
  exits_count: number;
  by_unit: Record<string, { entries_qty: string; exits_qty: string }>;
}

export interface ReplenishmentAlertItem {
  product_id: number;
  sku: string;
  name: string;
  category_name: string;
  unit: string;
  current_stock: string;
  min_stock: string;
  deficit: string;
  preferred_supplier_name: string | null;
  lead_time_days: number | null;
  stock_status: "BELOW_MIN" | "OUT_OF_STOCK";
}

export interface DashboardData {
  active_products_count: number;
  out_of_stock_count: number;
  below_min_stock_count: number;
  estimated_stock_value_brl: string;
  valuation_formula: string;
  valuation_disclaimer: string;
  period_start: string;
  period_end: string;
  entries_count: number;
  exits_count: number;
  adjustments_count: number;
  reversals_count: number;
  unit_summaries: UnitPeriodSummary[];
  daily_chart: DailyChartPoint[];
  replenishment_list: ReplenishmentAlertItem[];
}

export interface ImportRowError {
  line_number: number;
  sku: string | null;
  message: string;
}

export interface ImportValidRowPreview {
  line_number: number;
  sku: string;
  product_name: string;
  occurred_at: string;
  movement_type: string;
  reason_code: string;
  quantity: string;
  unit_snapshot: string;
  unit_cost: string | null;
  is_demand: boolean;
  is_synthetic: boolean;
}

export interface ImportPreviewOut {
  batch_id: number;
  filename: string;
  file_sha256: string;
  file_already_imported: boolean;
  status: string;
  total_rows: number;
  valid_rows: number;
  error_rows: number;
  duplicate_rows: number;
  is_synthetic: boolean;
  errors: ImportRowError[];
  sample_valid_rows: ImportValidRowPreview[];
  notice: string;
}

export interface ImportConfirmOut {
  batch_id: number;
  status: string;
  inserted_rows: number;
  confirmed_at: string;
  notice: string;
}

export interface ImportBatchSummary {
  id: number;
  filename: string;
  status: string;
  total_rows: number;
  valid_rows: number;
  error_rows: number;
  duplicate_rows: number;
  is_synthetic: boolean;
  created_at: string;
  confirmed_at: string | null;
}

export interface PurchaseSuggestionItem {
  product_id: number;
  sku: string;
  product_name: string;
  unit: string;
  available_stock: string;
  safety_stock: string;
  open_purchase_orders_qty: string;
  lead_time_days: number;
  lead_time_source: string;
  horizon_days: number;
  effective_coverage_days: number;
  predicted_demand_horizon: string;
  predicted_demand_effective_window: string;
  recommended_purchase_qty: string;
  prediction_interval_low: string | null;
  prediction_interval_high: string | null;
  model_version: string;
  generated_at: string;
  period_start: string;
  period_end: string;
  reason_summary: string;
  is_simulated: boolean;
  history_days_used: number;
}

export interface PurchaseSuggestionsResponse {
  model_connected: boolean;
  is_simulated: boolean;
  model_version: string | null;
  status_title: string;
  status_message: string;
  replenishment_rule_note: string;
  human_decision_notice: string;
  horizon_days: number;
  data_readiness: {
    active_products: number;
    operational_movements: number;
    operational_demand_events: number;
    historical_study_movements: number;
    stockout_periods_recorded: number;
  };
  items: PurchaseSuggestionItem[];
}

/* API-01: Version 1 report and provenance contracts */
export type ReportStatus =
  | "ready"
  | "calculating"
  | "insufficient_data"
  | "stale"
  | "empty";

export type ModelSource = "synthetic" | "legacy_calibrated";

export type CoverageStatus =
  | "available"
  | "stockout"
  | "unknown"
  | "uncovered";

export interface VersionedReport<T> extends PaginatedResponse<T> {
  schema_version: 1;
  status: ReportStatus;
  status_message: string | null;
}

export interface ModelProvenance {
  model_run_id: string;
  model_version: string;
  scenario: string;
  source: ModelSource;
  reference_date: string;
  trained_at: string;
  generated_at: string;
}

export interface ReplenishmentRow extends ModelProvenance {
  sku: string;
  product_name: string;
  warehouse: string;
  recommended_quantity: string;
  unit: string;
  policy: "dqn";
}

export interface ComparisonRow extends ModelProvenance {
  policy: "dqn" | "base_stock" | "s_s";
  seed: number;
  total_cost: string | null;
  fill_rate: string | null;
  stockout_days: number | null;
  mean_inventory: string | null;
  order_days: number | null;
}

export interface ImportedHistoryRow {
  record_id: string;
  sku: string;
  product_name: string;
  warehouse: string;
  event_date: string;
  event_type: string;
  quantity: string;
  unit: string;
  unit_cost: string | null;
  stock_availability: CoverageStatus;
  source: "firebird";
  batch_id: string;
  source_date: string | null;
}

export interface InventoryExceptionRow {
  sku: string;
  warehouse: string;
  reference_date: string;
  coverage: "stockout" | "unknown" | "uncovered";
  reason: string;
  source: "firebird";
  batch_id: string;
  source_date: string | null;
}

export interface CoverageCounts {
  available_days: number;
  stockout_days: number;
  unknown_days: number;
  uncovered_days: number;
}

export interface ImportQualityRow {
  batch_id: string;
  source: "firebird";
  warehouse: string;
  source_date: string | null;
  period_start: string | null;
  period_end: string | null;
  status: "imported" | "failed";
  imported_at: string | null;
  accepted_rows: number;
  rejected_rows: number;
  duplicate_rows: number;
  rejection_reasons: Record<string, number>;
  coverage: CoverageCounts | null;
}

export interface LegacyPreviewDiagnostic {
  dataset: string;
  line_number: number | null;
  reason: string;
}

export interface LegacyImportPreview {
  schema_version: 1;
  status: "ready" | "invalid";
  source: "firebird";
  warehouse: string;
  source_date: string | null;
  total_rows: number;
  valid_rows: number;
  rejected_rows: number;
  duplicate_rows: number;
  diagnostics: LegacyPreviewDiagnostic[];
}
