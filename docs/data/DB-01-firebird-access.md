# DB-01 · Legacy Firebird access and fingerprint

**Status:** catalog readable. A transportable backup was created, restored and matched. No Windows host was needed.
**Verified on:** 2026-11-23 · branch `feat/db-firebird`

## Source fingerprint

The original file was only hashed and copied. All engine access used disposable byte-for-byte copies outside Git.

| Field | Value |
|---|---|
| Original file | legacy `.FDB`, 694,894,592 bytes (two identical copies received) |
| SHA-256 | `23be4c6096dc566e64bb5a02b2475cef9e197590741db949dad7290f6c9e3d27`, the same before and after every run |
| Source engine (confirmed by Gabriel) | Firebird 1.5 on Windows |
| Page size | 4096 |
| ODS | 10.1 |
| SQL dialect | 3 |
| Implementation ID | 16 (Windows i386) |
| Creation date | 2021-03-10 16:52:13 |
| Default charset | WIN1252 |
| Attributes | forced writes, sweep interval 20000 |

## Verified access path (Firebird 1.5.6 Classic, Linux i386)

Firebird 1.5.6's `archMatrix10` ([`pag.cpp`, R1_5_6](https://github.com/FirebirdSQL/firebird/blob/R1_5_6/src/jrd/pag.cpp#L150-L183)) puts `CLASS_WINDOWS_I386` (16) and `CLASS_LINUX_I386` (19) in the same `archIntel86` group. A 32-bit Linux engine therefore opens the Windows file natively. Linux amd64 (24) is excluded from that group.

| Item | Value |
|---|---|
| Guest | colima profile `fbqemu`, `--arch x86_64 --vm-type qemu` (full QEMU emulation), Ubuntu 24.04 |
| Userland | `i386/debian:stretch` container, `--platform linux/386 --network none` |
| Engine | official `FirebirdCS-1.5.6.5026-0.i686.tar.gz` (SourceForge, SHA-1 `ea44d50e957ed7dd7b00801facfbc0d6f12eae4b` and MD5 `7b12df8ed62191d57e490dd33f3a78a6` match the published values) |
| Engine version | `LI-V1.5.6.5026 Firebird 1.5` |
| Binary | `isql`, `gbak`, `libfbembed.so.1.5.6`: ELF 32-bit LSB, Intel 80386. The guest kernel is x86_64 |
| Access | Classic local attach to `/work/db/legacy-copy.fdb`. No server process or TCP listener |
| Credentials | Random guest SYSDBA password set at image build time, stored root-only in the guest (`/opt/firebird/SYSDBA.password`). It is never printed or committed |

### Catalog (source copy)

| Object | Count |
|---|---|
| User tables | 201 (`SHOW TABLES` lists them all) |
| Views | 0 |
| User columns | 3,454 |
| Text columns by charset | WIN1252 865 · UNICODE_FSS 3 · database default 12 |
| Procedures | 13 |
| Triggers | 195 |
| Generators | 235 |
| Indices | 264 |
| Primary keys | 195 |
| Foreign keys | 60 |
| UDFs | 0 |
| DDL export (`isql -x`) | 7,219 lines, no errors |
| Total rows (201 tables) | 4,403,121, no count errors |

Largest tables by row count: `CARTOES_PDV` 2,404,498 · `ENTRADAS_SAIDAS` 651,066 · `VENDEDORES_VENDAS` 510,284 · `ITENS_CLIENTE_COMPRA` 152,212 · `ITENS_NOTA_FISCAL` 151,045. Tables relevant to inventory include `PRODUTOS`, `SALDO_PRODUTOS`, `ENTRADAS_SAIDAS`, `FORNECEDORES`, `PEDIDOS`, `ITENS_PEDIDO` and `NOTAS_FISCAIS`. DB-03 and DB-04 map these.

### Backup, restore and comparison

| Step | Result |
|---|---|
| `gbak -b -t -g` (transportable, no garbage collection) | rc 0, `.fbk` 412,850,688 bytes, SHA-256 `fbae1971298c8bf1e89e9e218fce5f03be25f1fed57a91875a2545648857afa6` |
| `gbak -c` to a separate database | rc 0, 570,019,840 bytes, ODS 10.1, dialect 3, implementation ID 19 |
| Schema (`isql -x`) restored vs source | identical except the two lines that name the database file path |
| Per-table row counts restored vs source | identical for all 201 tables (4,403,121 rows) |

Raw outputs live outside Git in `~/.estoquefacil-legacy-work/fb15/`: `out/` (DDL, counts, gbak logs, `compare.txt`), `backup/legacy.fbk` and `restore/legacy-restored.fdb`. Never commit them.

## Reproduce

```bash
brew install qemu lima-additional-guestagents
W=~/.estoquefacil-legacy-work/fb15; mkdir -p $W/db $W/dist $W/image $W/scripts/fb156cs
# FirebirdCS-1.5.6.5026-0.i686.tar.gz from https://firebirdsql.org/en/firebird-1-5/ → $W/image/
cp backend/legacy/firebird/fb156cs/Dockerfile $W/image/
cp backend/legacy/firebird/db01_catalog.sql $W/scripts/
cp backend/legacy/firebird/fb156cs/db01_fb15_inside.sh $W/scripts/fb156cs/
cp /path/to/original.FDB $W/db/legacy-copy.fdb          # byte-for-byte disposable copy
colima start fbqemu --arch x86_64 --vm-type qemu --cpu 4 --memory 4 --mount $W:w
colima ssh -p fbqemu -- sh -c "cd $W/image && sudo docker build --platform linux/386 -t fb156cs:local ."
colima ssh -p fbqemu -- sudo docker run --rm --platform linux/386 --network none -v $W:/work fb156cs:local \
  sh -c 'set -a; . /opt/firebird/SYSDBA.password; set +a; sh /work/scripts/fb156cs/db01_fb15_inside.sh'
```

The full pass takes about 20 minutes under QEMU. The colima Docker socket forward did not come up on the host, so Docker runs inside the guest through `colima ssh`. If the scripts change, copy them into `$W/scripts` again before a run: `sh` reads a script while running it, and editing it mid-run can derail the pass.

## Superseded attempt (commit a83be0a)

Firebird 2.5.9 `linux/amd64` rejected the file with `not a valid database`, because implementation class 24 is not compatible with class 16. A throwaway copy with the class byte patched failed with `wrong record length (183)`. Both results agree with the matrix above. They block only amd64 engines, not the i386 path. `db01_fingerprint.sh` is kept as the reproduction of that failure.

## Impact

- DB-03 and DB-04 can now use real data. They should work from `legacy.fbk` or the restored i386 database, through this Firebird 1.5.6 i386 guest.
- Restoring the `.fbk` on newer engines (Firebird 2.5/3+ amd64) has not been tried here. That belongs to the extraction cards.
