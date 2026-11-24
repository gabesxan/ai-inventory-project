# DB-15 · Second extract and safe repeat import

**Status:** the real slice reconciles across a clean import, a re-extraction rerun and a recovered failure: 49 checks `ok`, 0 `open`, and 1 `unavailable` (the dated balance). Run on a disposable PostgreSQL 16.

**Second extract:** `fb15/extracts/run-b`, a second export of the same snapshot. It differs from `run-a` only in `run.extracted_at_utc`; every table hash is equal. A *newer* snapshot would have to come from the source environment, so a newer-snapshot import is covered on fixtures only (an overlapping newer extract adds only new rows, and an older one is refused as `stale_extract`).

**Code:** `backend/legacy/reconcile.py` (`reconcile`, `snapshot_totals`), `backend/legacy/firebird/db15/db15_validate.py` (the real-data driver), `backend/legacy/tests/test_reconcile_pg.py`. Evidence outside Git: `~/.estoquefacil-legacy-work/fb15/out/db15/db15-validation.json`.

## What the validation does

1. **Re-extraction:** re-stages `run-b` with the DB-05/07/09/12 scripts and compares every staged output with `run-a`'s (content hash, gzip decompressed). All six are identical.
2. **Clean import** of `run-a`, reconciliation, then **import of `run-b`**: `already_imported`, the same batch, every total identical, reconciliation unchanged.
3. **Partial failure:** a failure injected after the history was staged rolls back everything (no product, history, coverage or rejection row; only a `failed` batch with `internal_error`). The real import afterwards recovers the **same batch** with totals equal to step 2.

Two defects found and fixed on the way: the batch fingerprint hashed `manifest.json` (which holds the extraction time) and the raw `.gz` (whose header holds a timestamp), so one snapshot looked like two. It now hashes the manifest without `run` and the decompressed content. The reconciliation also counted rejections across every batch of the warehouse; it now uses the latest imported batch.

## Reconciliation against the source ledger (extract `ENTRADAS_SAIDAS`)

Batch `fb-cf6383848e73fdde76569d0b`, warehouse `estoquefacil-fb15/1/local/1`, 2024-02-28 → 2026-11-18.

| Check | Expected (source) | Actual (database) |
|---|---|---|
| Ledger rows = staged rows + attributable rejections | 651,066 | 650,376 + 690 |
| Net daily sales (ledger `V`) in total | 3,569,797.446 | 3,569,797.446 |
| ... per SKU (6,928 series, sales + corrections + `V` rows refused by DB-07) | 0 mismatches | 0 |
| ... by unit | UN 2,923,499.444 · KG 645,947.383 · L 68.385 · M 264.234 · no unit 18.000 | identical (the 18.000 is the product without a unit, refused) |
| Receipts in total and per SKU | 13,825,130.714 | identical, 0 per-SKU mismatches |
| Verified demand (DB-07 summary) | 3,596,062.901 | identical |
| `sale_correction` / `supplier_return` quantity | −85.100 / 18,333.450 | identical |
| Product-days and series (DB-12) | 5,263,168 / 6,928 | identical, runs expand to the same days |
| Products, suppliers, groups | 6,997 / 563 / 63 | identical |
| Stock movements, `sum(current_stock)`, opening entries | 0 / 0.000 / 0 | identical |
| Dated balance | unavailable | **unavailable**, never zero: no physical count exists (DB-10) |

Every event type's rows and quantity also equal the DB-07 summary. Availability is never inferred as stockout or uncovered, and `available` appears only on sale days.

## Discrepancies

None open. The 690 rejections are accounted for: 239 DB-07 `reject` rows (the document does not move stock) and 451 receipts without a document and without a resolvable quantity (`ledger_without_document`, 0.000).

## Remediation instructions

- **Failed batch:** read its `failure_reason`, fix the cause, and run the same files again. The same batch is recovered, and nothing was published meanwhile.
- **`stale_extract`:** the extract ends before the stored coverage; import the newer extract, or delete the stored coverage on purpose first.
- **`coverage_day_mismatch`:** the series file and its index disagree; re-run DB-12 on the same extract.
- **`manifest_invalid`:** re-export the extract; DB-04's manifest check names the missing or changed files.

```sh
PYTHONPATH=backend python backend/legacy/firebird/db15/db15_validate.py <extract-a> <extract-b> <out-a> <work-out> --pg-socket DIR --pg-port N [--keep-db NAME]
```

## Verification

`LEGACY_PG_SOCKET=… LEGACY_PG_PORT=55432 TEST_DATABASE_URL=… PYTHONPATH=. pytest -q legacy/tests unit_tests tests` on an export of the commit. The driver exits 0 only when nothing is open.
