# DB-04 · Staged legacy extract with a manifest

**Status:** both acceptance criteria pass. The repeat-export check ran on real data; the missing/changed-file check ran on both real data and fixtures.
**Verified on:** 2026-11-23 · branch `feat/db-firebird` · consumes [DB-01](DB-01-firebird-access.md) and [DB-03](DB-03-source-identities.md)

## What it produces

`backend/legacy/firebird/db04/db04_export.py` runs inside the Firebird 1.5.6 i386 guest (`fb156cs-py` image: Python 3.5 + fdb 2.0.1 on `libfbembed.so`). It writes one directory per export:

```
<extract>/manifest.json            written last, by atomic rename
<extract>/<TABLE>/part-00001.csv   UTF-8 CSV with a header row, 100,000 rows per chunk, ordered by ID
```

Extracts live in `~/.estoquefacil-legacy-work/fb15/extracts/`, outside Git. `backend/legacy/manifest.py` validates them on the host (stdlib, Python 3.9+), and `load_ready()` is the gate DB-02 must call before loading.

## Allowlist (`db04/allowlist.json`)

28 tables, explicit columns only.
- **Included:** catalog (`PRODUTOS`, `GRUPOS`, `DEPARTAMENTOS`, `FAMILIAS`, `CAD_UNIDADES`); suppliers (`FORNECEDORES` with IDs, names, CNPJ and lead-time fields only; `CODIGO_REF_FORNECEDOR`); documents (`NOTAS_FISCAIS`, `ITENS_NOTA_FISCAL`, `SAIDA_PRODUTOS`, `ITENS_SAIDA_PRODUTOS`); movements and sales (`ENTRADAS_SAIDAS`, `VENDEDORES_VENDAS`, `ITENS_CLIENTE_COMPRA`); manual stock edits (`HIST_ALT_ESTOQUE_MANUAL`); and `CONFIGURACOES.I_LOJA`.
- **Excluded:** addresses, phones, e-mails, customer links (`ID_CLIENTE`), seller and user personal data, certificates, passwords, and free-text observations.
- **Empty tables are exported as header-only chunks:** `PEDIDOS`, `ITENS_PEDIDO`, `SALDO_PRODUTOS`, `CAD_BALANCO`, `ITENS_BALANCO`, `TRANSFERENCIA_PRODUTOS`, `ITENS_TRANSF_PROD`, `OUTRAS_EMBALAGENS`, `COMPOSICAO`, `TIPOS_ENTRADAS_SAIDAS`, `LOJAS`, `LOCALIZACOES`. This shows in the manifest that they were **empty in this snapshot**, which is not the same as zero balances or zero orders.

## Encoding, decimal and date rules

| Rule | Behavior |
|---|---|
| Charset | The connection charset is `WIN1252`. The driver decodes strictly, and output files are UTF-8. A non-WIN1252 text column in the allowlist aborts the export: fdb mis-sizes multibyte columns, which is how a UTF-8/`UNICODE_FSS` catalog truncation bug was found and fixed in the metadata query |
| NULL | `\N` (unquoted). Empty string → `""` |
| NUMERIC/DECIMAL | Fixed-point text with **exactly** the declared scale (`NUMERIC(6,4)` `1` → `1.0000`). A value that would need rounding aborts the export, and the validator rejects any value that doesn't have the declared scale |
| FLOAT/DOUBLE | `repr()`, typed `float32`/`float64` in the manifest, so consumers know FLOAT is single precision |
| DATE / TIME / TIMESTAMP | `YYYY-MM-DD` / `HH:MM:SS.ffffff` / `YYYY-MM-DDTHH:MM:SS.ffffff`. Local wall-clock time with no time zone, written **as stored**, future dates included |
| CHAR | Space padding is kept (for example `Un  `). Trimming happens downstream |
| Order | Ascending `ID` (`I_LOJA` for `CONFIGURACOES`), strictly increasing, checked at export and again at validation |
| Snapshot | All tables are read in **one read-only snapshot transaction**. The snapshot is identified by the `.fbk` SHA-256 (`fbae1971…afa6`), because attaching updates the working restore's header |

## Manifest contents

- Source engine, ODS and dialect; original `.FDB` and snapshot `.fbk` SHA-256.
- Scope: instance `estoquefacil-fb15/1`, branch 1, warehouse `…/local/1`, and the as-of date.
- The rules above and the allowlist SHA-256.
- Per table: typed columns (with scale and charset), row count, key digest (SHA-256 of the ordered IDs), and per chunk the file, rows, bytes, SHA-256 and first/last key.
- Quality counts and an `unresolved` list.

## How the DB-03 cases are handled

| Case | Count (this snapshot) | Extract policy |
|---|---|---|
| NF lines whose `ID_PRODUTO` is not in `PRODUTOS` | 54,624 lines / 7,336 IDs | Kept verbatim with the source ID; not dropped or remapped. DB-05 and DB-09 flag them |
| NF numbers reused within a type | 1,011 numbers / 2,279 headers | Kept as separate documents keyed by `NOTAS_FISCAIS.ID`; never merged on the number |
| Movements dated after the as-of date (2026-11-23) | 1 `C` row, dated 2026-12-31 | Kept with the stored `D_DATA` and flagged; not shifted or dropped |
| NF issued after the as-of date | 0 | — |
| Sale rows (`V`) with quantity ≤ 0 | 189 | Kept; DB-07 decides |

**Unresolved business meanings,** recorded in the manifest:
- The `S_OPERACAO` codes (only `V`/`C`/`A` are inferred).
- The daily-total nature of `ENTRADAS_SAIDAS`.
- `NOTAS_FISCAIS.S_TIPO` `A` vs `E`.
- `ITENS_NOTA_FISCAL.QUANTIDADE` values above the declared `NUMERIC(6,4)`.
- Header `QUANTIDADE` holds a line count, not units.

## Acceptance

Both exports read the same snapshot (`.fbk` `fbae1971…afa6`): 28 tables, 41 chunks, **1,505,884 rows**. Each validates with `python3 -m legacy.manifest validate`.

### 1. A repeated export of the same snapshot yields the same ordered row keys: PASS (real data)

- `python3 -m legacy.manifest compare run-a run-b` reports `keys_identical=True` and `checksums_identical=True` for all 28 tables, including `ENTRADAS_SAIDAS` (651,066 rows, 7 chunks) and `VENDEDORES_VENDAS` (510,284 rows, 6 chunks).
- The exports are byte-identical apart from `manifest.run.extracted_at_utc`.

### 2. A missing or changed input breaks validation and names the exact file: PASS (real data and fixture)

On a throwaway APFS clone of `run-b`:

```
$ python3 -m legacy.manifest validate tamper      # deleted one chunk, changed 1 byte in another
extract rejected:
  - missing: ENTRADAS_SAIDAS/part-00004.csv
  - changed: ITENS_NOTA_FISCAL/part-00002.csv (sha256/bytes differ from manifest)
$ mv tamper/manifest.json …; python3 -m legacy.manifest validate tamper
  - missing: manifest.json (incomplete or unfinished export) in …/tamper
```

- An export that was still running was also rejected for its missing `manifest.json`, which is the incomplete-batch case.
- An extract with normalized decimals (an earlier exporter version) was rejected with `decimal scale violated in CODIGO_REF_FORNECEDOR/part-00001.csv column F_ULT_VALOR_COMPRA at key 4738`.
- **FIXTURE tests** (`backend/legacy/tests/test_manifest.py`, 10 tests) cover a missing file, a changed file, an unexpected file, a missing manifest, a row-count tamper, out-of-order keys, a decimal-scale violation, numeric key order and an identical-export comparison.

## Reproduce

```bash
W=~/.estoquefacil-legacy-work/fb15
cp backend/legacy/firebird/db04/{db04_export.py,allowlist.json} $W/scripts/db04/
# one-time: image with Python + fdb on top of fb156cs (see DB-01)
#   FROM fb156cs:local; apt-get install python3 python3-pip; pip3 install fdb==2.0.1
colima ssh -p fbqemu -- sudo docker run --rm --platform linux/386 --network none -v $W:/work fb156cs-py:local \
  sh -c 'set -a; . /opt/firebird/SYSDBA.password; set +a; cd /work && python3 scripts/db04/db04_export.py \
    --db /work/restore/legacy-restored.fdb --out /work/extracts/run-a --as-of 2026-11-23 \
    --snapshot-sha256 <fbk sha256> --original-sha256 <FDB sha256>'
cd backend
PYTHONPATH=. python3 -m legacy.manifest validate $W/extracts/run-a
PYTHONPATH=. python3 -m legacy.manifest compare  $W/extracts/run-a $W/extracts/run-b
PYTHONPATH=. pytest -c /dev/null --rootdir . -p no:cacheprovider legacy/tests
```

Under QEMU, a full export takes about 40 minutes. Two exports can run concurrently, but only inside **one** container: Classic keeps its lock files in the container's `/tmp`.
