# DB-05 · Product and unit normalization

**Status:** both acceptance criteria pass. Packaged *receipts* are proven on real data. Packaged *sales* are fixture-only, because the source's sale tables have no unit or ratio column.
**Verified on:** 2026-11-23 · branch `feat/db-firebird` · input: the DB-04 extract `run-a` (validated with `load_ready`)

## Code

- `backend/legacy/products.py`: `normalize_products()` builds staged product records keyed by the DB-03 stable key and attaches quarantine issues. `to_base()` converts quantities to the stock unit only with a known ratio.
- `backend/legacy/extract.py`: a typed reader for a validated DB-04 extract.
- `backend/legacy/firebird/db05/db05_products.py`: runs on the real extract and writes `products.csv` and `summary.json` to `~/.estoquefacil-legacy-work/fb15/out/db05` (outside Git).

## v1 product mapping

| v1 `products` field | Source | Rule |
|---|---|---|
| `sku` | `PRODUTOS.CODIGO_INTERNO` | trimmed; unique (6,998 distinct values) |
| `name` | `DESCRICAO` | trimmed; WIN1252 decoded in DB-04 |
| `barcode` | `CODIGO_BARRAS` | only when it is a valid GTIN-8/12/13/14 (4,080). The 2,918 internal codes such as `0000000003066` stay in staging as `source_code` |
| `unit` | `UNIDADE` | `Un→UN`, `Kg→KG`, `Lt→L`, `Mt→M`. An unknown unit (`Ce`, 1 product) is quarantined |
| `is_active` | `ATIVO` | `1` → true |
| `min_stock` | `ESTOQUE_MIN` | `NUMERIC(6,3)` fits `Numeric(14,3)` |
| `category_id` | `GRUPO` / `DEPARTAMENTO` | **DB-06** |
| `current_stock` | — | **DB-10** (dated opening entry). `ESTOQUE_ATUAL` is not copied |
| `unit_cost` | `PRECO_CUSTO` (scale 3) | **not mapped here**: v1 stores 2 decimals, so copying would round. DB-09 owns cost provenance |
| `preferred_supplier_id`, `lead_time_days` | — | **DB-06 / DB-11** |

Staging keeps the source unit, weighed flag (`PESADO`), units per box (`UNIDADES_CAIXA`), group and department IDs, and the issue list.

## Units and conversions (real data)

| Product unit (source → v1) | Weighed | Products |
|---|---|---|
| Un → UN | no | 6,265 |
| Kg → KG | yes | 674 |
| Kg → KG | no | 52 |
| Lt → L | yes / no | 4 / 1 |
| Mt → M | yes | 1 |
| Ce → (unknown) | no | 1 (**quarantined**) |

`CAD_UNIDADES` also lists `Am`, `Cx`, `Dz`, `M3`, `Pc` and `Sc`, but no product uses them.

**The receipt ratio is documented by the source itself.**
- `ITENS_NOTA_FISCAL.S_UNIDADE_MEDIDA` is `UN` or `KG` on every line with a known product (UN→UN 94,381 · KG→KG 1,679 · UN→KG 361), yet `QUANTIDADE` counts purchase packs: `I_UNIDADES_CAIXA` is present and ≥ 1 on every entry line (50,476 lines above 1).
- Compared with the source's own stock entries (`ENTRADAS_SAIDAS` `C`, from 2024-02-28) per product and day:

| Candidate base quantity | Product-days equal to the stock entry (of 40,455) |
|---|---|
| `QUANTIDADE` as labelled | 17,894 |
| `QUANTIDADE × F_FATOR_CONVERSAO` | 17,927 |
| **`QUANTIDADE × I_UNIDADES_CAIXA`** | **40,340 (99.7%)** |
| `to_base()` (the rule below) | 40,339 |

**Rule:**
- When the label is the product's own unit or a package unit and a documented ratio is present, base quantity = qty × ratio. With ratio 1 it is the same unit.
- A package label without a positive ratio is **unconvertible**.
- A label of another unit kind (353 `UN` lines on `KG` products) is **unconvertible** and never guessed.
- **Packaged receipts with ratio > 1:** 22,446 product-days match exactly, 2 differ and 69 have no stock row. These are listed for DB-09.

## Quarantine and training eligibility

| Item | Count | Effect |
|---|---|---|
| Products staged | 6,997 of 6,998 | — |
| Quarantined products | 1 (`unknown_unit`) | not imported or trained |
| Duplicate SKU / duplicate barcode | 0 / 0 | the rules are active and fixture-tested |
| Sale rows (`V`) in base units, eligible | 609,692 | — |
| Sale rows excluded (quarantined product) | 12 | not trained |
| Entry lines convertible (`pack_ratio` 50,386 · `same_unit` 44,365) | 94,751 | — |
| Entry lines unconvertible (`UN→KG`) | 353 | not trained |
| NF lines whose product is missing (DB-03) | 54,624 | no product, so they can't be normalized; DB-09 flags them |

## Acceptance

### 1. A packaged sale converts only with a known ratio: PASS (fixture). The real-data analogue is receipts

- The real sale tables (`ENTRADAS_SAIDAS` `V`, `VENDEDORES_VENDAS`, `ITENS_CLIENTE_COMPRA`) record quantities in the product's stock unit and have **no unit or ratio column**, so a real packaged sale can't be shown. All 609,692 eligible sale rows convert as `same_unit`.
- **FIXTURE** (`backend/legacy/tests/test_products.py`): `2 CX` with ratio 12 → 24 UN. `2 CX` with no ratio, or ratio 0 → unconvertible. A `UN`-labelled receipt line with `I_UNIDADES_CAIXA = 12` → 24.
- **Real packaged receipts:** 22,446 product-days convert with the documented ratio and equal the source stock entry.

### 2. Equivalent totals reconcile in base units; unconvertible rows stay out of training: PASS (real data and fixture)

- **Real:** 40,339 of 40,454 receipt product-days reconcile in base units with the source's stock effect. The 353 unit-mismatch lines and the 12 sale rows of the quarantined product are excluded.
- **FIXTURE:** 2 CX × 6 + 12 UN = 24 UN, and the `FD` line without a ratio is excluded.

## Unresolved, for the next cards

1. **186 count-unit (`UN`) products have fractional sale quantities** (4,168 rows). Kept as recorded; DB-07 decides whether they are demand.
2. 115 receipt product-days don't reconcile with the stock effect (2 packaged, 39 unit-ratio, 74 without a stock row). DB-09 should review them.
3. Whether `UNIDADES_CAIXA` on the product matches the latest line's `I_UNIDADES_CAIXA` hasn't been checked. The line value is the documented one.
4. The `Ce` unit's meaning is unknown, so that product stays quarantined.

## Reproduce

```bash
cd backend
PYTHONPATH=. python3 legacy/firebird/db05/db05_products.py ~/.estoquefacil-legacy-work/fb15/extracts/run-a ~/.estoquefacil-legacy-work/fb15/out/db05
PYTHONPATH=. pytest -c /dev/null --rootdir . -p no:cacheprovider legacy/tests
```
