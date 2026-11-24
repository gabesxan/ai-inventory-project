# DB-12 · Daily coverage and stock availability

**Status:** all three acceptance criteria pass.
- The source-period criterion passes on real data.
- The "missing day" and "known stockout" criteria pass on FIXTURE, because the real snapshot has no store-level gaps and no availability history.
- The real series are published with availability marked **unknown**, never zero.

**Verified on:** 2026-11-23 · branch `feat/db-firebird`

**Inputs:**
- the validated DB-04 extract `run-a`, used for coverage and products (quarantine from DB-05)
- DB-07 `events.csv`: demand = `pos_sale` + `invoice_sale`; days that can't be determined = `unverified_outbound`, `pending_document`, `canceled_document` or `sale_correction`
- DB-09 `stock_receipts.csv`: the posted receipt effect

The input SHA-256s are recorded in `summary.json`.

## Day statuses (`backend/legacy/coverage.py`)

Each product-day inside a series period gets exactly one status:

| Status | Rule | Usable as uncensored demand |
|---|---|---|
| `sale` | verified demand > 0 | yes |
| `true_zero` | no demand on a covered day **and** stock known to be available | yes |
| `zero_unknown_availability` | no demand on a covered day, availability unknown | **no** |
| `known_stockout` | availability evidence says out of stock (censored) | **no** |
| `unknown_quantity` | the day has rows whose demand can't be determined | **no** |
| `calendar_gap` | the store ledger posted **nothing** that day, so the day is missing, not zero | **no** |

**Coverage rule:** a day is covered when the store ledger (`ENTRADAS_SAIDAS`, any operation) has rows for it, from 2024-02-28 (the ledger start; the 2001-01-01 outliers are excluded) to the snapshot date.

**Availability rule:** a sale proves stock on that day. With no physical opening stock (DB-10), nothing else is known, so a zero-sale day is `zero_unknown_availability`. If DB-10 later gets a dated count, the same builder accepts a per-day availability map.

## Real-data result (`db12_series.py`, outputs in `~/.estoquefacil-legacy-work/fb15/out/db12`, outside Git)

| Item | Value |
|---|---|
| Warehouse | `estoquefacil-fb15/1/local/1` (DB-03) |
| Store period | 2024-02-28 → 2026-11-18: **995 calendar days, 995 covered, 0 gaps** |
| Series | 6,928 (non-quarantined products with demand or receipts in the period). Each starts at the product's first activity |
| Product-days | 5,263,168 |
| `sale` | 609,488 |
| `unknown_quantity` | 112 |
| `zero_unknown_availability` | 4,653,568 |
| `true_zero` / `known_stockout` / `calendar_gap` | 0 / 0 / 0 |
| Uncensored days | 609,488 (sales only) |

The files are:
- `series.csv.gz`: one row per product-day, with status, demand, receipts, availability and an uncensored flag.
- `series_index.csv`: per series, the key, SKU, unit, warehouse, `period_start`, `period_end`, `source`, availability basis and status counts.

## Acceptance

### 1. A missing day is not zero demand: PASS (fixture). Real data has no gaps

- **FIXTURE:** a day without ledger postings becomes `calendar_gap` with `demand = None` and is not uncensored.
- A covered zero-sale day with unknown stock becomes `zero_unknown_availability`, again not zero.
- **Real:** 0 store gaps in 995 days. The 4,653,568 zero-sale days are all marked `zero_unknown_availability`, so none is counted as zero demand.

### 2. A known stockout is excluded from uncensored calibration: PASS (fixture only)

- **FIXTURE:** a day with `available = False` becomes `known_stockout`. `calibration_demand()` returns only the sale and true-zero days (`[4, 0]`).
- The real snapshot has no balance history, so there are no known stockouts (`known_stockout_source: none`).

### 3. Each series identifies its source period: PASS (real data and fixture)

- **Real:** all 6,928 index rows carry `period_start`, `period_end` and `source` (`ENTRADAS_SAIDAS ledger 2024-02-28..2026-11-18; snapshot fbk fbae1971298c`), plus the availability basis.
- **FIXTURE:** the period and source are checked exactly.

## For IA-07 / API-04 (other workstreams)

- Real uncensored history = sale days only.
- Calibration should treat `zero_unknown_availability` as censored. Gabriel decided on 2026-11-24 that there is no opening stock (DB-10), so this stays the rule unless a dated physical count is supplied later.
- The quantities are base units (DB-05), with the unit given per series.
