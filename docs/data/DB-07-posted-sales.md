# DB-07 · Posted sales and other outbound movements

**Status:** acceptance passes on a mixed FIXTURE. The same classifier runs on the real extract and its totals reconcile to the source ledger.
**Verified on:** 2026-11-23 · branch `feat/db-firebird` · input: DB-04 extract `run-a`; units from DB-05

## Which source is the sale

| Source | Grain | Finding | Use |
|---|---|---|---|
| `ENTRADAS_SAIDAS` `V` | one row per product per day (PDV 1) | the stock ledger's posted POS total. 609,704 rows, 2024-02-28..2026-11-18, plus 4 rows dated 2001-01-01 with qty ≤ 0 | **demand source** |
| `VENDEDORES_VENDAS` | ticket line with time | every one of its product-days exists in the ledger `V`, but it covers only 66,528 of 609,700 product-days (seller-attributed tickets). It has 1,800 negative lines | not demand. It's a subset, so adding it would double count |
| `ITENS_CLIENTE_COMPRA` | coupon line of identified customers | a customer subset (DB-03) | not demand |
| `NOTAS_FISCAIS` type `A` + lines | outbound fiscal document | matches ledger `A`, `D` and `_` rows on product, day and base quantity | classifies those rows by CFOP |
| `SAIDA_PRODUTOS` type `P` + lines | internal outbound document | matches ledger `P` on 150 of 151 product-days; the linked `ID_NOTA_FISCAL` isn't in the extract | internal outbound |

**Event time:** the ledger only has a **date** (`D_DATA`, local). DB-07 carries `day`, not a timestamp. Times exist only on the `VENDEDORES_VENDAS` subset.

## Classification (`backend/legacy/outbound.py`)

1. **Matching.** A ledger row is linked to documents only when the documents' summed line quantities, in base units (DB-05 rule: `QUANTIDADE × I_UNIDADES_CAIXA`), equal the ledger total for that operation, product and day.
2. **Class.** The class then comes from the document's **CFOP**, a national fiscal code, and its status.

| Event type | Rule | Demand |
|---|---|---|
| `pos_sale` | ledger `V` with qty > 0 | **yes** |
| `invoice_sale` | `A`/`D`/`_` linked to a type-A document with a sale CFOP (`5102`, `6102`, `5403`…) and status `1` | **yes** |
| `supplier_return` | CFOP `5202`/`6202` ("DEVOLUCAO PARA FORNECEDOR") | no |
| `loss` | CFOP `5927` ("LANCAMENTO BAIXA DE ESTOQUE", loss write-off) | no |
| `warranty_exchange` | CFOP `6949`/`5949` ("TROCA GARANTIA") | no |
| `transfer` | CFOP `5151`/`5152`/`6152`… (none in this snapshot; the transfer tables are empty) | no |
| `pending_document` / `canceled_document` | document status `0` / `3` (**inferred**: 402 of 453 type-A documents are status `1`) | no |
| `internal_outbound` | ledger `P` linked to `SAIDA_PRODUTOS` type `P` (**meaning unresolved**: loss, consumption or production) | no |
| `unverified_outbound` | no matching document, or documents of mixed classes | no |
| `sale_correction` | ledger `V` with qty < 0 (handed to DB-08) | no |
| `reject` | zero quantity, document without stock movement, quarantined or missing product (DB-05), or dated after the snapshot | no |

## Real-data result (`db07_sales.py`)

| Event type | Rows | Qty (base units) |
|---|---|---|
| `pos_sale` | 609,503 | 3,569,864.546 |
| `invoice_sale` | 130 | 26,198.355 |
| `internal_outbound` | 152 | 282.834 |
| `supplier_return` | 25 | 18,333.450 |
| `loss` | 23 | 1,374.830 |
| `warranty_exchange` | 24 | 105.602 |
| `pending_document` | 25 | 5,181.097 |
| `unverified_outbound` | 95 | 9,070.896 |
| `sale_correction` | 18 | −85.100 |
| `reject` | 239 | 18.000 (227 zero-quantity rows, 12 rows of the quarantined product) |

- **Verified demand:** 609,633 rows, **3,596,062.901** base units, 995 days, 2024-02-28 → 2026-11-18.
- **Reconciliation to the ledger:** `pos_sale` + `sale_correction` + `V` rejects = ledger `V` total, 3,569,864.546 − 85.100 + 18.000 = **3,569,797.446**. All 610,234 outbound ledger rows are classified, with none dropped.
- 163 type-A NF lines couldn't be converted (unit mismatch or missing product), so their ledger rows remain `unverified_outbound` unless another document matches.
- Raw events are in `~/.estoquefacil-legacy-work/fb15/out/db07/events.csv`, outside Git, with each row's movement key, event type and linked NF keys.

## Acceptance: PASS (fixture)

**Mixed fixtures produce verified sales totals without counting pending documents, transfers, losses or canceled sales as demand.**
- `backend/legacy/tests/test_outbound.py` uses 13 mixed rows: a POS sale, a posted invoice sale, pending and canceled invoices, a loss, a transfer, a supplier return, a warranty exchange, an internal outbound, an undocumented row, a zero row, a negative total and mixed documents.
- Demand = 12 + 5 = **17.000**. Every other row gets its own event type.
- The real run above shows the same separation on source data. There are no transfers in this snapshot, so the transfer case is **fixture-only**.

## Unresolved

1. The `I_NFE_STATUS` meanings (`0` pending, `3` canceled) are inferred. Only status `1` counts.
2. The meaning of `SAIDA_PRODUTOS` type `P`, and the 86 `ID_NOTA_FISCAL` values that point outside the extract.
3. The 95 `unverified_outbound` rows (42 `A`, 51 `_`, 1 `D`, 1 `P`) have no matching document. They are excluded from demand until a source proves what they are.
4. 186 count-unit products with fractional `V` quantities (DB-05) are kept as recorded.
5. Negative `V` totals (18) and the `VENDEDORES_VENDAS` negative lines go to DB-08.
