# DB-06 · Categories and supplier links

**Status:** the acceptance criterion passes on **real data**. It was imported twice into an isolated, disposable PostgreSQL with the v1 schema; a fixture regression test covers the same logic.
**Verified on:** 2026-11-23 · branch `feat/db-firebird` · input: DB-04 extract `run-a`; products from DB-05

## Mapping (`backend/legacy/catalog_links.py`)

| v1 target | Source | Rule | Real result |
|---|---|---|---|
| `categories.name` | `GRUPOS.S_DESCRICAO` | one v1 category per source group | 63 groups; names unique and non-empty |
| `products.category_id` | `PRODUTOS.GRUPO` | always the product's own group | 6,997 of 6,997 staged products resolve; 0 missing |
| department (staged) | `PRODUTOS.DEPARTAMENTO` → `DEPARTAMENTOS` | kept as an attribute; a missing department is **unresolved** | 808 products point to a department that doesn't exist |
| `suppliers.name`, `suppliers.document` | `NOME_FANTASIA` or `RAZAO_SOCIAL`; `CNPJ` (14 digits) | display identifiers only: no contact data, no CPF | 563 suppliers; CNPJ unique where present |
| supplier associations (`legacy_product_suppliers`) | `CODIGO_REF_FORNECEDOR` pairs + `PRODUTOS.ULT_FORNECEDOR` | only pairs whose supplier exists | 12,244 associations across 338 suppliers |
| `products.preferred_supplier_id` | the associations above | set **only** when exactly one supplier is evidenced | 4,190 products |
| unresolved (`legacy_unresolved_links`) | — | several candidate suppliers, or a missing department | 1,057 `preferred_supplier_ambiguous` + 808 `department` |

- **Reconciliation:** every category, supplier and product is reconciled by its stable origin key (`legacy_origin`: entity + DB-03 key → v1 id). A rerun updates instead of duplicating.
- **Missing relationships stay unset** where v1 allows it (`preferred_supplier_id` NULL).
- **Quarantined products** (DB-05) are not imported.

The importer creates `legacy_origin`, `legacy_product_suppliers` and `legacy_unresolved_links` itself for now. **DB-13** (blocked by API-01) must turn them into an additive Alembic migration, together with DB-10's tables.

## Acceptance: PASS (real data, disposable PostgreSQL)

**"Products retain their linked categories, a supplier filter resolves valid associations, and ambiguous links remain explicitly unresolved."**

`db06_links.py` creates a throwaway database on the local Unix-socket-only cluster, runs `alembic upgrade head` (v1), imports the real plan **twice**, checks it, and drops the database.

| Check | Result |
|---|---|
| Rerun | the counts after the 1st and 2nd import are identical: 63 categories, 563 suppliers, 6,997 products, 12,244 associations, 1,865 unresolved |
| Products keep their category | 6,997 checked: 0 category mismatches, 0 name mismatches |
| Supplier filter on associations | for all 338 linked suppliers, the products in the DB equal the plan (0 mismatches) |
| Supplier filter on `preferred_supplier_id` | 0 mismatches; 4,190 products |
| Ambiguous links | 1,057 products with several suppliers: **0** got a preferred supplier, and all 1,057 are listed in `legacy_unresolved_links` |

The fixture regression in `backend/legacy/tests/test_catalog_links_pg.py` checks categories, filtering by supplier, a single preferred supplier, the ambiguous product and the rerun.

Outputs are `summary.json` and `unresolved_links.csv` in `~/.estoquefacil-legacy-work/fb15/out/db06`, outside Git.

## Unresolved

1. 1,057 products have several supplier candidates. `ULT_FORNECEDOR` (the last supplier) is recorded as an association but is not treated as "preferred".
2. 808 products reference departments missing from `DEPARTAMENTOS`.
3. `FORNECEDORES.PRAZO_ENTREGA` (declared delivery time) is **not** mapped to `default_lead_time_days`. Lead times must be measured (DB-11), and `PEDIDOS` is empty.
