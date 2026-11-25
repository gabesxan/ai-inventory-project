# DB-04 follow-up · Complete read-only export of the legacy Firebird

**Status:** complete and verified. All 201 user tables and every column were exported from the existing restored copy, with no write to Firebird or to any PostgreSQL.

**This is an old snapshot, not newer data.** The source is the restore of the `.fbk` with sha256 `fbae1971298c8bf1e89e9e218fce5f03be25f1fed57a91875a2545648857afa6` (original `.fdb` sha256 `23be4c60…3d27`), the same snapshot as `run-a` and `run-b` (as of 2026-11-23, latest posted ledger day 2026-11-18). A newer Firebird file from Gabriel's environment would be needed for newer data.

**The data contains personal data and credentials** (customers, users, card transactions). It stays on the local disk with owner-only permissions, outside Git. Nothing from it is in this repository, the notes or the chat.

## Artifacts (outside Git, `~/.estoquefacil-legacy-work/fb15/extracts/`)

| Path | Content |
|---|---|
| `full-a/` | 201 tables, 239 chunks, 439 MB, `manifest.json` (types, row counts, key digests, sha256 per chunk). Mode 0700 |
| `full-a-meta/counts.tsv` | Per table: source `COUNT(*)` in the same snapshot transaction, rows exported, DB-01 reference, match |
| `full-a-meta/errors.log` | Empty after the fix below |
| `full-a-meta/source-schema.sql`, `restored-schema.sql`, `source-counts.tsv` | DDL and the DB-01 counts |
| `full-fornecedores/`, `full-fornecedores-meta/` | The re-export of the one table that failed, kept as provenance |

## Result

| | |
|---|---|
| Tables | 201 of 201 (82 with data, 119 empty and proven empty by a header-only chunk) |
| Rows | 4,403,121 exported = 4,403,121 in the DB-01 source counts |
| Divergences | 0 of 201 tables |
| Largest | `CARTOES_PDV` 2,404,498 · `ENTRADAS_SAIDAS` 651,066 · `VENDEDORES_VENDAS` 510,284 |
| Validator | `python -m legacy.manifest validate`: OK, 201 tables, 239 chunks |
| Synthetic keys | 6 tables without an integer primary key use a `__ROW` counter, flagged in the manifest |

## What went wrong, and the fix

`FORNECEDORES` (563 rows) failed in the main run with a `UnicodeDecodeError`: a text field holds byte `0x8d`, which Python's strict cp1252 leaves undefined. The other 200 tables were unaffected. It was re-exported alone with `--lenient-decode`, which maps the five bytes cp1252 leaves undefined to the code point of the same value, counted per table: **3 bytes** in total, all in this table. `db04_merge_export.py` then merged it into the main export, refusing different snapshots and any table that had not failed. The manifest records `merged_from`. Every other table uses the strict decode.

## Search for an opening count or a dated balance, over the complete catalog

No physical count exists. Empty: `CAD_BALANCO`, `ITENS_BALANCO`, `SALDO_PRODUTOS`, `TRANSFERENCIA_PRODUTOS`, `ITENS_TRANSF_PROD`, `PEDIDOS`, `ITENS_PEDIDO`. `PRODUTOS.ULT_INVENTARIO` is null for every product. The tables outside the old allowlist that carry quantities were read:

- **`HISTORICO_PRODUTOS`** (6,998 rows, 12 monthly slots; `DATAS.I_REF_MES_HIST_PROD` = 10). It is a monthly aggregate of the same **book** balance, not a count. Slot 11 equals `ESTOQUE_ATUAL` for 6,812 of 6,998 products, with 2,494 negative. Its entries match the ledger exactly in 6 of 12 months and diverge in the other 6, and its exits never match the ledger sales. Its balances grow monotonically from 0.49 M to 3.59 M units over the year, which a physical count would not do.
- **`HIST_ALT_ESTOQUE_MANUAL`**: 48 manual adjustments to the book balance (46 products, 19 before the ledger starts). Not a count, not an opening balance.
- **`ESTOQUE_ATUAL`**: undated book balance, 2,494 negative of 6,998.
- Other tables with "quantity" columns (`HISTORICO_CARGAS`, `OPCOES_PRODUTO`, `VENDAS_HORA`, `MOV_OCORRENCIAS_CAIXA`, …) count transmissions, options, hourly sales and cash events, not stock.

**Conclusion:** the decision stands: **no opening stock**, availability stays unknown, `source_date` stays null, and lead times stay unavailable (no purchase orders). Importing this full export into the application's PostgreSQL remains **pending** until Gabriel provides the target instance and a verified backup, a physical count with its date (if one exists), a confirmed snapshot date and an order → receipt history.

## Reproduce

```sh
W=~/.estoquefacil-legacy-work/fb15
cp backend/legacy/firebird/db04/{db04_export.py,db04_export_all.py} $W/scripts/db04/
colima ssh -p fbqemu -- sudo docker run --rm --platform linux/386 --network none -v $W:/work \
  -e OUT=/work/extracts/full-a fb156cs-py:local sh /work/scripts/db04/run_all.sh        # about 3 hours under QEMU
# a table that fails the strict decode: -e ONLY=<TABLE> -e LENIENT=1 -e OUT=<new dir>, then
python3 backend/legacy/firebird/db04/db04_merge_export.py <full-a> <full-a-meta> <part> <part-meta>
cd backend && PYTHONPATH=. python3 -m legacy.manifest validate $W/extracts/full-a
```

`run_all.sh` sources the guest SYSDBA credentials without echoing them; it lives next to the scripts in `$W/scripts/db04/`.
