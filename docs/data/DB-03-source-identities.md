# DB-03 · Source identities and warehouse scope

**Status:** both acceptance cases pass. Cross-branch collisions are proven with fixtures because the source has one branch. The join check uses real data.
**Verified on:** 2026-11-23 · branch `feat/db-firebird`
**Source:** the validated DB-01 restore `legacy-restored.fdb` (Firebird 1.5.6 Classic i386 guest, see [DB-01](DB-01-firebird-access.md)). Raw key exports stay in `~/.estoquefacil-legacy-work/fb15/out/db03`, outside Git.

## Company and branch

| Fact | Evidence |
|---|---|
| One company | `CONFIGURACOES` has 1 row and 1 CNPJ root |
| One branch per database | `CONFIGURACOES.I_LOJA = 1`. Every branch column in every checked table is `1` |
| `LOJAS` cannot serve as the branch master | `LOJAS` is empty (0 rows), so it can't anchor branch keys |
| IDs are per database | Every `ID` comes from a per-database generator (`GEN_<TABLE>_ID` in the `*_BI` triggers). Another branch's database would reuse the same IDs |

**Rule for DB-04:**
- Every stable key carries the *source instance*: the system plus `CONFIGURACOES.I_LOJA`, so `estoquefacil-fb15/1`.
- Each key is `<instance>/<entity>/<ID>`.
- The branch comes from the row's own branch column when the table has one. Otherwise it is inherited from the instance.
- The company is an attribute, not a key part.
- `legacy/identity.py` implements these rules.

## Key map

| Entity | Source table | Source key | Branch column | Stable key | Natural/diagnostic key | Observed uniqueness |
|---|---|---|---|---|---|---|
| Product | `PRODUTOS` | `ID` (PK) | `ID_LOJA`, always NULL, so products are instance-wide | `…/produto/ID` | `CODIGO_INTERNO`, `CODIGO_BARRAS` (UNQ) | 6,998 rows: ID, internal code and barcode each have 6,998 distinct values |
| Supplier | `FORNECEDORES` | `ID` (PK) | none | `…/fornecedor/ID` | `I_NUMERO` (UNQ). CNPJ is optional | 563 rows, 563 `I_NUMERO`. 9 have no CNPJ, and no CNPJ is shared |
| Location / warehouse | (branch) | `I_LOJA` | the key itself | `…/local/<branch>` | — | `LOCALIZACOES` is empty and no product sets `LOCALIZACAO`, so warehouse = branch |
| Fiscal document | `NOTAS_FISCAIS` | `ID` (PK) | `ID_LOJA` | `…/nf/ID` | (branch, `S_TIPO`, `MODELO`, `SERIE`, `NUMERO`, `ID_FORNECEDOR`, `ID_CLIENTE`) and the 44-digit `S_NFE_CHAVE_ACESSO` | 25,965 headers (E 25,512 · A 453) |
| Fiscal line | `ITENS_NOTA_FISCAL` | `ID` (PK) | inherited from the header | `…/nf_item/ID` | parent `ID_NOTA_FISCAL` (FK, cascade) | 151,045 lines |
| Outbound document | `SAIDA_PRODUTOS` / `ITENS_SAIDA_PRODUTOS` | `ID` / `ID` | `LOJA` | `…/saida/ID`, `…/saida_item/ID` | parent `ID_SAIDA_PRODUTOS` (FK) | 86 headers, 219 lines |
| Stock movement | `ENTRADAS_SAIDAS` | `ID` (PK) | `I_LOJA` | `…/mov/ID` | (branch, `I_PDV`, `S_OPERACAO`, `ID_PRODUTO`, `D_DATA`), unique except for 2 groups | 651,066 rows, all `I_PDV = 1` |
| POS coupon (sale document) | `ITENS_CLIENTE_COMPRA` | line `ID` | `I_LOJA` | `…/cupom/<branch>/<pdv>/<date>/<S_CUPOM>` | — | 152,212 lines. 55,629 coupons, but only 54,560 distinct numbers |
| Purchase order | `PEDIDOS` / `ITENS_PEDIDO` | `ID` | `ID_LOJA` | (reserved) `…/pedido/ID` | — | **both empty** |
| Per-branch stock | `SALDO_PRODUTOS` | `ID` | `ID_LOJA` | — | (`ID_PRODUTO`, `ID_LOJA`) | **empty** |

## Joins and cardinalities

| Join | Cardinality | Real-data result |
|---|---|---|
| `NOTAS_FISCAIS.ID` 1 → N `ITENS_NOTA_FISCAL.ID_NOTA_FISCAL` | 1 to 1..146 | 0 orphan lines and 0 headers without lines |
| `ITENS_NOTA_FISCAL.ID_PRODUTO` N → 1 `PRODUTOS.ID` | many-to-one, **no FK** | 54,624 lines (7,336 missing product IDs: E 54,469, A 155) reference products that no longer exist |
| `NOTAS_FISCAIS.ID_FORNECEDOR` N → 0..1 `FORNECEDORES.ID` | many-to-one | 0 orphans |
| `ENTRADAS_SAIDAS.ID_PRODUTO` N → 1 `PRODUTOS.ID` | many-to-one (FK) | 0 orphans |
| `SAIDA_PRODUTOS.ID` 1 → N `ITENS_SAIDA_PRODUTOS` | 1 to 0..N | 0 orphan lines, 1 header without lines |
| Coupon (branch, PDV, date, `S_CUPOM`) 1 → N `ITENS_CLIENTE_COMPRA` | 1 to N | the number alone is not enough: 1,058 numbers repeat across PDVs or dates |
| `ENTRADAS_SAIDAS.ID_MOVIMENTO` | — | a single distinct value in all 651,066 rows, so it is **not** a document link |

## Demonstration warehouse

- **Valid-sale filter:** `ENTRADAS_SAIDAS.S_OPERACAO = 'V'` and `F_QUANTIDADE > 0`, the product exists in `PRODUTOS`, and `D_DATA <= 2026-11-23` (the extract date).
- **Ranking:** most sale days, then most valid sale rows, then the lowest branch ID. The branch ID is the stable source key and acts as the tie-breaker.

| Branch | Valid sale rows | Sale days | Products sold | First | Last |
|---|---|---|---|---|---|
| **1 (selected)** | 609,515 | 995 | 3,982 | 2024-02-28 | 2026-11-18 |

**Excluded:** 189 `V` rows with quantity ≤ 0 (18 negative, 171 zero). They include the 4 rows dated 2001-01-01, so valid history starts on 2024-02-28.

Branch 1 is the only candidate, so the tie-breaker was not needed. Location key: `estoquefacil-fb15/1/local/1`.

## Acceptance

### 1. Colliding document numbers in two branches stay distinct: PASS (fixture plus real-data analogue)

- **Real data:** only one branch exists, so 0 numbers appear in two or more branches and a real cross-branch case can't be shown.
- **Within branch 1:** 1,011 NF numbers are reused within the same type across 2,279 headers. All 25,965 stable keys stay distinct. The largest case is one entry number shared by 6 headers, still 6 distinct keys.
- **Coupons:** 54,560 coupon numbers expand to 55,629 distinct coupons under the (branch, PDV, date, number) key.
- **FIXTURE** (`backend/legacy/tests/test_identity.py`):
  - The same number, series and supplier in branches 1 and 2 of one database gives distinct stable keys and distinct natural keys.
  - Two branch databases whose generators both produced `NOTAS_FISCAIS.ID = 10` also give distinct keys, because the source instance is part of the key.
  - Coupons with the same number on different PDVs, dates or branches stay distinct.

### 2. The header-to-line join keeps the checked counts and quantities: PASS (real data)

| Check | Value |
|---|---|
| Lines exported vs lines joined to a header | 151,045 = 151,045 (0 orphans) |
| Headers with at least one line | 25,965 of 25,965 |
| Header `QUANTIDADE` (it holds the declared **line count**) equal to the joined line count | 25,965 of 25,965 |
| Sum of line `QUANTIDADE`, all lines vs joined lines | 3,158,535.6297 = 3,158,535.6297 |
| Distinct line stable keys | 151,045 |

Two independent paths agree: the SQL in `db03_join_check.sql` runs on Firebird 1.5, and `db03_verify.py` runs on the exported keys.

A fixture test also checks counts and quantity sums through the staged keys, including a 13,020-unit line.

## Ambiguities for DB-04 and later

1. **No movement-type catalogue.** `TIPOS_ENTRADAS_SAIDAS` is empty. The codes are inferred: `V` sale (609,704 rows), `C` purchase or entry (40,832, **dated up to 2026-12-31, after the extract**), `A` adjustment (249), `P` (153), `D` (28), `_` (100). DB-07 and DB-08 need to confirm them.
2. **`ENTRADAS_SAIDAS` rows look like per-day totals.** They are unique at (branch, PDV 1, operation, product, date) except for 2 groups, while the coupon lines show 7 PDVs (1–6, 11). DB-07 should treat them as daily totals per product, not individual tickets.
3. **NF lines with missing products.** 54,624 lines (36%) point to 7,336 product IDs that are not in `PRODUTOS` (deleted products, and there is no FK). This affects DB-05 and DB-09.
4. **NF natural duplicates.** 9 natural-key groups and 3 access keys appear more than once. The stable keys keep them apart, and DB-08/DB-09 decide whether they are re-imports or corrections.
5. **The header `QUANTIDADE` column is a line count, not units.** `ITENS_NOTA_FISCAL.QUANTIDADE` is declared `NUMERIC(6,4)` but holds values up to 13,020 (5,934 lines are ≥ 100), because Firebird stores it as a scaled 32-bit integer. Stage it as a wide decimal.
6. **Empty `PEDIDOS`, `SALDO_PRODUTOS`, `LOJAS` and `LOCALIZACOES`.** DB-11 has no purchase orders to recover lead times from in this extract. DB-10 must take opening stock from another source, such as `PRODUTOS.ESTOQUE_ATUAL` or a reconstruction.

## Reproduce

```bash
W=~/.estoquefacil-legacy-work/fb15; mkdir -p $W/scripts/db03
cp backend/legacy/firebird/db03/*.sql backend/legacy/firebird/db03/db03_extract.sh $W/scripts/db03/
colima start fbqemu   # Firebird 1.5.6 i386 guest from DB-01
colima ssh -p fbqemu -- sudo docker run --rm --platform linux/386 --network none -v $W:/work fb156cs:local \
  sh -c 'set -a; . /opt/firebird/SYSDBA.password; set +a; sh /work/scripts/db03/db03_extract.sh'
cd backend && PYTHONPATH=. python3 legacy/firebird/db03/db03_verify.py $W/out/db03   # writes summary.json
PYTHONPATH=. pytest -c /dev/null --rootdir . -p no:cacheprovider legacy/tests        # fixture acceptance
```

The key export takes about 15 minutes under QEMU. Firebird 1.5 SQL has no derived tables, no `TRIM` and no `ABS`, so the scripts use `SET LIST`, `BETWEEN` tolerances and Python for the grouping.
