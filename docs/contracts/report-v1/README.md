# Inventory report contracts, version 1

The new routes below use the existing `/api` prefix and bearer authentication. Each requires the `ADMIN` role. A missing or expired session returns 401. A signed-in operator receives 403 with the standard FastAPI `detail` field. The existing report and AI routes retain their current contracts.

| Method and path | Row schema | Filters |
| --- | --- | --- |
| GET `/api/reports/imported-history` | `ImportedHistoryRow` | `start_date`, `end_date`, `sku`, `warehouse`, `event_type`, `source` (`firebird`) |
| GET `/api/reports/replenishment` | `ReplenishmentRow` | `sku`, `warehouse` |
| GET `/api/reports/comparison` | `ComparisonRow` | `source`, `model_run_id`, `scenario` |
| GET `/api/reports/inventory-exceptions` | `InventoryExceptionRow` | `start_date`, `end_date`, `sku`, `warehouse`, `coverage` |
| GET `/api/ai/imports/legacy/batches` | `ImportQualityRow` | `warehouse`, `batch_id` |

JSON reports use `schema_version: 1` and the existing `items`, `total`, `page`, `page_size`, and `total_pages` envelope. Pages are numbered from 1. The default size is 25 and the supported range is 1–200. An empty result has one page. Dates use ISO 8601, and date filters are inclusive. Decimal quantities, costs and ratios serialize as strings. A JSON `null` denotes unavailable data, while zero denotes an observed or computed zero. Warehouse identifiers are strings so source identifiers can be preserved.

| HTTP | Status field | Meaning |
| --- | --- | --- |
| 200 | `ready` | Stored results match the selected scope. |
| 200 | `calculating` | Work is pending or running and a result is unavailable. |
| 200 | `insufficient_data` | The selected scope lacks eligible inputs. |
| 200 | `stale` | A stored result exists and its inputs or freshness window have expired. Return it with its original provenance. |
| 200 | `empty` | The filter matches no stored records. |
| 403 | — | Use the standard error body in the `forbidden` fixture. |

The optional explanation is represented by the nullable `status_message`. A temporarily unavailable API uses its HTTP failure status, and the caller handles request failures separately from an empty result. A report GET only reads stored results.

Imported history preserves the event classification, base quantity and unit from the verified mapping. Keep sales, receipts, returns and other outbound events distinct. Availability is `available`, `stockout`, `unknown` or `uncovered`. Unknown availability and missing coverage do not imply stockouts or zero demand. `source_date` is the source snapshot date when verified, and `event_date` is the date of the individual record. Only row-safe batch identifiers, reason codes and aggregates appear in import-quality reports.

Model rows carry an opaque run ID, version, scenario, source, reference date and UTC training and generation timestamps. `synthetic` denotes simulation inputs and `legacy_calibrated` requires verified eligible legacy inputs. The suggestion quantity uses the SKU's unit. The comparison reports a fill-rate fraction in the range 0–1 and one row per policy and held-out seed for the selected run and scenario. Missing metrics are nullable.

Imported history, comparison and import-quality exports use `export=csv` and the same filters, row order and exact decimal precision as JSON. They export the full filtered set before pagination with one row per record and empty cells for null values. Include provenance columns. Order history by event date descending then record ID ascending, comparison by run, scenario, seed and policy ascending, and batches by import date descending with nulls last then batch ID ascending. For nested quality fields, encode rejection reasons and coverage as JSON in their CSV cells.

DB-13 uses the `LegacyImportPreview` shape for its read-only preview result. Counts describe the staged extract. Diagnostics contain a dataset, one-based line number when known, and a row-safe reason code. Preview is separate from confirmation and does not change operational stock.

The [shared fixtures](fixtures.json) exercise all response states and report shapes. Every record is invented, including the examples with `source: "firebird"`. The schema definitions are in [reports.py](../../../backend/app/schemas/reports.py). These routes are delivered in the subsequent API and database cards.

Validate the fixtures from the repository root with `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/unit_tests/test_report_contracts.py`.
