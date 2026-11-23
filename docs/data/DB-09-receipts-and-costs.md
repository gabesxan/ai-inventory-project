# DB-09 · Stock receipts and cost provenance

**Status:** both acceptance criteria pass on real data, with fixture backup.
**Verified on:** 2026-11-23 · branch `feat/db-firebird` · input: DB-04 extract `run-a`; units from DB-05

## Source facts

| Fact | Evidence |
|---|---|
| The posted stock effect of an entry is the ledger `ENTRADAS_SAIDAS` `C` row (per product and day) | `C` starts on 2024-02-28 and has 40,832 product-days |
| Entry documents are `NOTAS_FISCAIS.S_TIPO = 'E'` (25,512) with lines in purchase packs | base qty = `QUANTIDADE × I_UNIDADES_CAIXA` (DB-05; equals the ledger on 99.7% of product-days) |
| Receipt date = header `DATA_SAIDA_ENTRADA` | the date that matches the ledger `D_DATA` |
| `VALOR_UNITARIO` (scale 4) = price per **purchase** unit | `F_VALOR_TOTAL` = qty × price on 142,752 of 149,573 lines |
| `F_CUSTO_PRODUTO_UNIT` (scale 3) = cost per **base** unit recorded by the source | equals price ÷ units on 60,011 lines and is higher on 83,718 (taxes and freight inferred, **unresolved**). `F_CUSTO_PRODUTO_TOTAL` = it × qty × units |
| Ledger `C.F_CUSTO` | always 0, so it is not a cost source |

## Receipt classes (line CFOP, `backend/legacy/receipts.py`)

| Class | CFOP suffix | Lines | Stock receipt from a supplier? |
|---|---|---|---|
| `supplier_purchase` | 101, 102, 401, 403, 117, 118 | 128,547 | **yes** |
| `supplier_bonus` | 910, 911 | 3,298 | **yes** (bonus goods; the invoice value is recorded) |
| `transfer_in` | 151, 152, 409 | 0 (transfer tables are empty) | no |
| `customer_return` | 201, 202, 410, 411 | 73 | no (DB-08) |
| `other_entry` | 949 | 6,910 | no (adjustment-like) |
| `use_consumption`, `fixed_asset`, `service`, `utility`, `fuel_consumption` | 556/407, 551, 933, 253, 653 | 10,681 | no |
| `unknown_cfop` | — | 64 | no |

The class travels with each line and each stock-history day, so DB-12 and DB-11 can use only supplier receipts while the physical stock effect stays complete.

## Cost provenance

Every receipt line keeps three cost values plus a status:
- `price_per_purchase_unit`: `VALOR_UNITARIO` as recorded, for example `49.9900`.
- `invoice_cost_per_base_unit`: price ÷ units per pack, derived and quantized to 6 decimals.
- `recorded_cost_per_base_unit`: `F_CUSTO_PRODUTO_UNIT` as recorded, scale 3.
- `cost_status`: `known` 149,564 · `explicit_zero` 9 (kept as 0) · `unknown` 0. An unknown cost stays null; nothing is invented.

## Real-data result (`db09_receipts.py`)

| Entry-line status | Lines | Meaning |
|---|---|---|
| `posted` | 41,803 | documented, and the quantity equals the ledger stock effect |
| `posted_quantity_mismatch` | 134 | a ledger effect exists but differs (41 product-days, 9,571 UN), for review |
| `no_stock_effect` | 75 (8 documents, **18,003,846 UN**) | no ledger effect, so canceled or never posted. **Never counted** |
| `before_ledger_coverage` | 52,739 | before 2024-02-28; can't be verified against the ledger, so kept as documented-only |
| `unconvertible` | 353 | `UN` lines on `KG` products (DB-05) |
| `missing_product` | 54,469 | product ID not in `PRODUTOS` (DB-03) |

**Stock history** = the ledger effect with provenance: `documented` 40,339 product-days, `quantity_mismatch` 41, `ledger_without_document` 452 (4.000 KG in total; almost all are zero-quantity rows).

## Acceptance

### 1. Receiving totals reconcile by period and unit: PASS (real data)

| Unit | Ledger `C` | Documented | Mismatch | Without document |
|---|---|---|---|---|
| UN | 13,799,513.100 | 13,789,942.100 | 9,571.000 | 0.000 |
| KG | 25,617.614 | 25,613.614 | 0 | 4.000 |

- In all **69 month × unit cells**: ledger = documented + mismatch + without document (exact Decimal).
- Documented = the sum of posted lines in base units.
- **FIXTURE** in `test_receipts.py` reconciles a canceled receipt by period and unit.

### 2. Costs keep decimal precision, and canceled receipts don't inflate stock history: PASS (real data and fixture)

- Source prices stay at scale 4 and recorded costs at scale 3. Derived costs use 6 decimals, for example 49.9900 / 12 = 4.165833 (fixture).
- Explicit zero stays 0, and unknown stays null.
- The 8 documents with no posted stock effect (18,003,846 UN) are excluded from stock history. **FIXTURE:** a canceled 12 UN receipt never enters the month total.

## Unresolved, for the next cards

1. 41 mismatch product-days (134 lines) and 452 ledger entries without a document. Their stock effect is kept with this provenance.
2. The cost uplift in `F_CUSTO_PRODUTO_UNIT` (taxes, freight, ST?) is not documented. Both costs are kept.
3. There's no receipt cancel status on type-`E` documents (`I_NFE_STATUS` is null on 25,447). Cancellation is inferred only from a missing stock effect.
4. 2014–2024 receipts (52,739 lines) predate the ledger. They can support supplier and cost history, but **not** stock-history verification.
5. Lead times: `PEDIDOS` is empty (DB-11).
