# DB-02 · Apply legacy data idempotently to PostgreSQL

**Status:** both acceptance criteria pass on fixtures and on the real extract, in a disposable PostgreSQL 16.

**Code:** `backend/legacy/apply.py` (`apply_extract`, CLI `python -m legacy.apply`), built on the DB-13 schema (`0002_legacy_staging`) and the shared reader `legacy/history.py`. Operational stock is never touched.

## Behavior

- **One transaction.** Manifest gate → DB-06 catalog (categories, suppliers, products, by origin key) → history events → DB-12 coverage → rejections and the batch row. Any error rolls everything back, so a failed batch never publishes a partial snapshot.
- **Batch identity** is `fb-` + a hash of source system, warehouse and the extract fingerprint (manifest + staged inputs + DB-12 series). The same files give the same batch. A batch already `imported` is returned as `already_imported` without writing.
- **Failure is recorded separately** as a `failed` batch with a reason code (`manifest_invalid`, `stale_extract`, `coverage_day_mismatch`, `coverage_warehouse_mismatch`, `unknown_day_status`, `internal_error`). A later successful run of the same files replaces that row. A manifest that cannot be read has no stable identity and is refused without a row.
- **Repeat and overlap:** history rows are unique per `(warehouse_key, record_id)`. A newer overlapping extract adds only new rows (the rest are counted as duplicates). Coverage is replaced for the warehouse. An extract that ends before the stored coverage is refused (`stale_extract`).
- **Attributable rejections:** `legacy_import_rejections` keeps dataset, file line (when the row has one), reason code and source key. Responses and reasons never carry source values. A product that did not reach the catalog is rejected as `product_not_in_catalog`.
- **No opening stock.** No `stock_movements`, no `SALDO_INICIAL`, no change to `products.current_stock`, and `ESTOQUE_ATUAL` is not read. Availability stays `unknown` except on a sale day. The DB-08 ticket corrections are not applied.
- **Day-level coverage is preserved in the database** (`legacy_coverage_ranges`, 409,640 runs), reconciled per product against the DB-12 index (`coverage_day_mismatch` otherwise). The API reads tables, not the local artifact `fb15/out/db12/series.csv.gz`.

```sh
cd backend
python -m legacy.apply <extract-dir> <out-dir> --pg-socket DIR --pg-port N --pg-db NAME [--source-date YYYY-MM-DD]
```

Use a dedicated database that is already at `alembic upgrade head`.

## Real-data result (`run-a`, database `fb15_import_check`, disposable)

| | First import | Second import |
|---|---|---|
| Status | `imported` | `already_imported`, same batch |
| History events | 650,376 (sale 609,633 · receipt 40,381 · return 43 · other_outbound 319) | identical |
| Rejections | 690 (239 `document_does_not_move_stock`, 451 `receipt_quantity_unavailable`) | identical |
| Products / categories / suppliers | 6,997 / 63 / 563 | identical |
| Coverage series / ranges | 6,928 / 409,640 | identical |
| Coverage days | available 609,488 · unknown 4,653,680 · stockout 0 · uncovered 0 | identical |
| `stock_movements`, `sum(current_stock)`, `legacy_opening_entries` | 0, 0.000, 0 | identical |

Sale quantity 3,596,062.901 = DB-07 `pos_sale` 3,569,864.546 + `invoice_sale` 26,198.355. Evidence: `~/.estoquefacil-legacy-work/fb15/out/db02/` (apply JSON and before/after totals), outside Git.

## Verification

- Fixture suite on a throwaway PostgreSQL 16: `LEGACY_PG_SOCKET=… LEGACY_PG_PORT=55432 PYTHONPATH=. pytest -q legacy/tests unit_tests` → 76 passed.
- Covered by `legacy/tests/test_apply_pg.py`: import without stock change, the same files twice (all table counts identical), failure atomicity with retry on the same batch, coverage that does not add up, an unreadable extract, a newer overlapping extract, and an older extract refused.
