# DB-08 · Returns, reversals and corrections

**Status:** both acceptance criteria pass.
- The partial-return criterion passes on **FIXTURE**: the real data has no partial returns, since all 1,726 linked reversals are full.
- The unlinked-correction criterion passes on **real data** and on fixture.

**Verified on:** 2026-11-23 · branch `feat/db-firebird` · input: DB-04 extract `run-a`, DB-07 events, DB-05 units

## What the source can prove

| Source | Level | Link to the original | Real counts |
|---|---|---|---|
| Ledger `ENTRADAS_SAIDAS` `V` | daily **net** total per product | none: gross and returns **can't be separated** here | 18 negative daily totals (−85.100) are **unlinked corrections** |
| `VENDEDORES_VENDAS` (ticket subset, see DB-07) | ticket line | **proven** when a negative line has a positive line for the same product on the same coupon and day | 1,800 negative lines: **1,726 linked** (all full reversals) and **74 unmatched credits** |
| Entry NFs with CFOP x201/x202/x411 (customer returns) | document line | none: no reference to the original sale | 66 lines, 712,682 base units. Flagged `unlinked_customer_return`; the size suggests erroneous documents, so they need review |
| Type-A NFs with CFOP x202 (returns **to suppliers**) | document line | **proven** by `S_CHAVE_NFE_DEVOLUCAO` = the original entry NF's access key | 23 lines linked to the original line (same product); 9 whose original isn't in the extract |

## Rules (`backend/legacy/returns.py`)

- Every return or correction keeps its **effective date** and a **signed delta** (−qty), its source, the original ID when one is proven, and a quality flag otherwise.
- `net_sales(sales, returns)`:
  - Gross = the positive sales; net = gross − returns.
  - Each return id is applied **once**, whatever happens upstream.
  - A linked return is capped at what remains of its original line, and any excess is flagged `exceeds_original`.
  - Unlinked credits reduce net and are flagged for review (`unlinked_credit`, `unmatched_ticket_credit`, `negative_daily_total`, `unlinked_customer_return`).
- **Linking on tickets:** a negative line goes to a positive line on the same coupon with enough remaining quantity, preferring an exact match.
- **Float32 quantities:** `F_QUANTIDADE` is FLOAT, so values are quantized to 3 decimals, which is the source quantity domain.

## Real-data result (`db08_returns.py`, outputs in `~/.estoquefacil-legacy-work/fb15/out/db08`, outside Git)

| Ticket subset | Quantity |
|---|---|
| Gross (positive lines) | 583,856.999 |
| Reversals (1,726 linked + 74 unmatched) | 2,242.977 |
| **Net** | **581,614.022**, which equals the sum of all ticket lines exactly |

- `corrections.csv` has 1,891 rows: every reversal, correction and return line with its effective date, signed delta, link and flag.
- **Ledger level:** net only. DB-07's demand already uses these daily net totals, so the ticket reversals are **not** subtracted again, which would double count.

## Acceptance

### 1. A partial return reduces net sales only once: PASS (fixture)

- **FIXTURE** (`backend/legacy/tests/test_returns.py`): returning 2 of a 5-unit sale gives net 4.250 (gross 6.250). Delivering the same return twice still gives net 4.250, and `applied = ["r1"]`.
- A further return beyond the original is capped and flagged.
- **Real:** all 1,726 linked ticket reversals are full cancellations, so there's no real partial case.

### 2. An unlinked correction stays traceable with its effective date and a quality flag: PASS (real data and fixture)

- **Real:** each of the 18 negative ledger totals is listed with its movement key, effective date (`D_DATA`), signed delta and `negative_daily_total`. The same holds for the 74 unmatched ticket credits (`unmatched_ticket_credit`) and the 66 customer-return lines (`unlinked_customer_return`).
- **FIXTURE:** the unlinked correction keeps `effective_date` and `flag`, and reduces net once.

## Unresolved

1. The customer-return NFs (712,682 base units in 66 lines) look erroneous. They aren't applied to demand automatically; review is needed.
2. 9 supplier returns reference NFs that aren't in the extract.
3. The ledger can't split gross and returns. Gross/return reporting exists only for the ticket subset (66,528 of 609,700 product-days, see DB-07).
