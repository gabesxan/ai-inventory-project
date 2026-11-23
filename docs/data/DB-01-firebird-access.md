# DB-01 · Legacy Firebird access and fingerprint

**Status:** real-data track blocked. Reproducible evidence below. A transportable backup is needed from the source environment.
**Verified on:** 2026-11-23 · branch `feat/db-firebird`

## Source fingerprint

The file was read and hashed only. All engine access used disposable copies outside Git.

| Field | Value |
|---|---|
| Original file | legacy `.FDB`, 694,894,592 bytes (two identical copies received) |
| SHA-256 | `23be4c6096dc566e64bb5a02b2475cef9e197590741db949dad7290f6c9e3d27` |
| Page size | 4096 |
| ODS | 10.1 (Firebird 1.5 on-disk format) |
| SQL dialect | 3 |
| Implementation ID | 16 (written by a Windows x86 build of the engine) |
| Creation date | 2021-03-10 16:52:13 |
| Attributes | forced writes, sweep interval 20000 |
| Transactions | next 39,052,947 · oldest active 39,039,079 |
| Default charset | not readable (catalog not opened) |

The original hash was identical before and after every run. The disposable copy's hash also stayed unchanged because the engine never attached.

## What was tried

The engine was Firebird 2.5.9 (`LI-V2.5.9.27139`), `linux/amd64` (`jacobalberty/firebird:2.5-ss@sha256:6efd02fc…84ac`). It ran under Rosetta in a dedicated colima profile with `--network none`. Firebird 2.5 is the newest engine that can open ODS 10.x, because Firebird 3+ requires ODS 12.

1. **Unmodified copy:** `isql` attach failed with `SQLSTATE HY000 file … is not a valid database`. The header's implementation class 16 does not match the engine's native class 24, so the engine refuses the cross-platform file. `gstat -h` can still read the header.
2. **Diagnostic, on a second throwaway copy with only the header class byte changed to 24:** attach failed with `internal Firebird consistency check (wrong record length (183), file: vio.cpp line: 1248)`. Record layouts differ between the Windows x86 build and Linux amd64. Patching is therefore not a valid access path, and that copy was deleted.

## Reproduce

```bash
LEGACY_FDB=/path/to/original.FDB FIREBIRD_PASSWORD=… \
  backend/legacy/firebird/db01_fingerprint.sh   # exit 2 = blocked, evidence in $LEGACY_WORK/out/blocker.txt
```

The script needs a Docker context that can run `linux/amd64`. On Apple Silicon, for example: `colima start fbx86 --vm-type vz --vz-rosetta --mount ~/.estoquefacil-legacy-work:w`. Outputs go to `~/.estoquefacil-legacy-work/out` by default and must never be committed. After the catalog opens, the same script exports DDL (`isql -x`), the catalog summary (`db01_catalog.sql`) and per-table row counts.

## Request to the source environment

Run on the Windows host that serves this database (Firebird 1.5/2.x, same machine or same engine build):

```bat
gbak -b -t -g -user SYSDBA -password <pw> "C:\path\BANCO.FDB" BANCO.fbk
```

`-t` makes the backup transportable, and `-g` skips garbage collection, so the live data is not modified. Send `BANCO.fbk` with the engine version reported by `gbak -z`. The local track then restores it with `gbak -c` on Firebird 2.5 amd64 and reruns this script. The other option is a Windows x86 Firebird 1.5/2.5 environment that opens the `.FDB` natively.

## Impact

- DB-03 and DB-04 can't do real-data work until the backup arrives. Synthetic and fixture paths are unaffected.
- The API, IA and FE cards that only need fixtures or synthetic data are unaffected.
