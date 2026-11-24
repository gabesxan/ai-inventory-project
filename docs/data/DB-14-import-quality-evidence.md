# DB-14 · Import and data-quality evidence

**Status:** both acceptance criteria pass on fixtures and on the real import (disposable PostgreSQL 16).

**Route:** `GET /api/ai/imports/legacy/batches`, API-01 `ImportQualityRow` inside the `VersionedReport` envelope. Admin only: 401 without a session, 403 `{"detail": "Acesso restrito a administradores."}` for an operator (the same `require_admin` as the other AI routes).

**Code:** `backend/app/api/legacy_imports.py` (own router, one registration line in `app/main.py`), `backend/app/services/legacy_import_service.py` (read-only SQL over `legacy_import_batches`), tests in `backend/tests/test_legacy_imports_api.py`.

## Response

| Field | Source |
|---|---|
| `batch_id`, `warehouse`, `source_date`, `period_start`, `period_end`, `status` (`imported` or `failed`) | `legacy_import_batches` (`warehouse_key` is the source warehouse, `estoquefacil-fb15/1/local/1`) |
| `imported_at` | UTC (`…Z`), null for a failed batch |
| `accepted_rows`, `rejected_rows`, `duplicate_rows` | The loader's counts for that batch. `accepted_rows` equals the batch's `legacy_history_events`, `rejected_rows` its `legacy_import_rejections` |
| `rejection_reasons` | Reason code → count. Codes only: no source value, key or line content |
| `coverage` | Product-day totals `available_days`, `stockout_days`, `unknown_days`, `uncovered_days` (the DB-12 statuses grouped as in `legacy_coverage_ranges.coverage`), or null |

Filters: `warehouse`, `batch_id`. Pagination: `page` from 1, `page_size` 1–200 (default 25). `status` is `ready`, or `empty` with `status_message` "Nenhum lote de importação no recorte selecionado." (one page). Order: import date descending with nulls last, then `batch_id` ascending. Never returned: the extract fingerprint, source record keys, `failure_reason`.

**CSV (`export=csv`)** covers the whole filtered set before pagination, in the JSON order, with values taken from the same model, so JSON and CSV cannot differ. Columns are `batch_id, source, warehouse, source_date, period_start, period_end, status, imported_at, accepted_rows, rejected_rows, duplicate_rows, rejection_reasons, coverage`. The last two hold compact JSON with sorted keys, and null is an empty cell. An empty filter returns the header only.

## Gap to settle with API-01

`ImportQualityRow` has no `failure_reason`, so an administrator sees a `failed` batch but not why (the code is stored: `stale_extract`, `coverage_day_mismatch`, `manifest_invalid`, `internal_error`, …). Adding a nullable `failure_reason: str | None` in the contract would close it. It was not added here because `reports.py` is Codex's file.

## Real data (extract `run-a`, database `fb15_import_check`)

One batch, `fb-d4079f9af3e41935cca15bf4`: `imported`, warehouse `estoquefacil-fb15/1/local/1`, 2024-02-28 → 2026-11-18, `source_date` null, accepted 650,376 · rejected 690 (`document_does_not_move_stock` 239, `receipt_quantity_unavailable` 451) · duplicates 0, coverage available 609,488 · unknown 4,653,680 · stockout 0 · uncovered 0. An operator gets 403. These equal the loader's totals.

## Verification

`TEST_DATABASE_URL=… LEGACY_PG_SOCKET=… LEGACY_PG_PORT=55432 PYTHONPATH=. pytest -q legacy/tests unit_tests tests` → 92 passed (6 new). Covered: admin reasons and counts per batch, 403 and 401, filters, pagination and order, JSON/CSV parity, no leaked internals, and totals equal to what `apply_extract` wrote.
