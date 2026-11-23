# DB-10 · Dated opening-stock snapshot

**Status:**
- Both acceptance criteria pass on a **FIXTURE** imported into an isolated, disposable PostgreSQL.
- **The real opening stock is unavailable.** The snapshot holds no verified physical balance, so no real opening entry was created. A decision is needed (see the end).

**Verified on:** 2026-11-23 · branch `feat/db-firebird` · input: DB-04 extract `run-a`; products from DB-05

## What the source holds

| Candidate balance source | Real content | Usable as opening stock? |
|---|---|---|
| `CAD_BALANCO` + `ITENS_BALANCO` (physical inventory counts with a closing date) | **0 rows** | it would be the only eligible source, but it's empty |
| `SALDO_PRODUTOS` (per-branch balance) | **0 rows** | — |
| `PRODUTOS.ULT_INVENTARIO` (last inventory date) | NULL for all 6,998 products | — |
| `PRODUTOS.ESTOQUE_ATUAL` (system book balance) | 4,395 positive (sum 17,243,954.184) · 109 zero · **2,494 negative** | **no.** It isn't a physical count, and the source stores no balance date. It is consistent with the last day's ledger for only 112 products |
| `HIST_ALT_ESTOQUE_MANUAL` (manual stock edits) | 48 rows, 2022-08-31..2026-09-22 | no. It covers few products and isn't a count |

Empty count tables **don't** establish zero balances, so no product gets a zero opening.

## Implementation (`backend/legacy/opening.py`)

- **`select_snapshot(extract)`:**
  - Only a closed `CAD_BALANCO` (dated by `DATA_ENCERRAMENTO`) with counted, non-negative `ITENS_BALANCO` lines is eligible.
  - Everything else goes to the discrepancy report: book balances (`book_balance_not_physically_verified`), `negative_book_balance`, `negative_count`, `not_counted`, and `product_missing_or_quarantined`.
- **`import_snapshot(conn, snapshot, user_id)`** runs in **one transaction** in the dedicated database:
  - `legacy_opening_snapshots` stores the snapshot's **actual source date**, its warehouse key and a label.
  - `legacy_opening_entries` holds one row per product key, which is the primary key, so there is at most one opening per SKU ever.
  - A positive balance creates one v1 `stock_movements` row (`ENTRADA` / `SALDO_INICIAL`, balance 0 → qty) and updates `products.current_stock`. Its note reads `Saldo inicial legado em <date> (<source>)`.
  - A counted zero is recorded without a movement, because v1 requires quantity > 0.
  - Re-importing the same snapshot is a no-op. A **different** snapshot for a product with an opening, or a product that already has stock or movements, is **refused** and never reset.
  - These two tables are created by the importer for now. **DB-13** must turn them into an additive Alembic migration. DB-13 is blocked by API-01.

## Real-data result (`db10_opening.py`)

- Selected snapshot: **none**, because `no_physical_count_in_snapshot (CAD_BALANCO/ITENS_BALANCO empty; SALDO_PRODUTOS empty)`.
- Eligible opening entries: **0**. Nothing was written to any database.
- Discrepancy report (`~/.estoquefacil-legacy-work/fb15/out/db10/discrepancies.csv`, outside Git): 6,998 products. 2,494 are `negative_book_balance` and 4,504 are `book_balance_not_physically_verified`.
- **Date label of the book balances:** the source stores no balance date. The latest posted ledger day is **2026-11-18** and the snapshot was received on 2026-11-23. Any use of these balances must say "book balance at the 2026-11-18 ledger", not "today".

## Acceptance

Both tests are in `backend/legacy/tests/test_opening_pg.py`. Each run creates a throwaway database on a local Unix-socket-only cluster, applies the v1 Alembic schema (`alembic upgrade head`), and drops the database afterwards.

### 1. Re-importing a snapshot can't reset stock or duplicate opening entries: PASS (fixture, PostgreSQL)

The fixture snapshot has 10 UN, a counted 0 and an unknown SKU.
- **First import:** 1 movement, 1 zero recorded and 1 missing product. Stock is {10, 0, 0}.
- **Same snapshot again:** 0 created and 2 already imported. State is identical.
- **Another snapshot with 99 UN:** refused (`opening_exists_from_other_snapshot`), and stock stays 10.
- **A product with existing stock:** refused (`product_already_has_stock_history`).

### 2. An old snapshot is labelled with its actual date: PASS (fixture, PostgreSQL)

- A snapshot counted on **2019-03-31** is stored with `source_date = 2019-03-31` on the snapshot and on every entry.
- The movement note says "Saldo inicial legado em 2019-03-31", not the import date.

## Decision needed (Gabriel)

The real opening stock can't be established from this snapshot. Options:

1. **Provide a physical count** (a `CAD_BALANCO` export or a dated spreadsheet) for the demonstration warehouse. It would import through the path above.
2. **Accept the book balance `ESTOQUE_ATUAL`** as an *unverified* opening dated 2026-11-18. Only for the 4,395 positive balances, with the 2,494 negative ones left out. DB-12 would then have to mark availability as book-based.
3. **No opening stock.** DB-12 publishes demand and receipts only, and availability stays unknown. Nothing has to be invented.

Until one of these is chosen, DB-12 treats stock availability as **unknown** rather than zero.
