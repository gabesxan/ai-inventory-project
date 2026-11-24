#!/bin/sh
# DB-01 · runs INSIDE the isolated Firebird 1.5.6 Classic i386 container (--network none).
# Expects /work/db/legacy-copy.fdb (disposable byte-for-byte copy) and SYSDBA creds in env
# (ISC_USER/ISC_PASSWORD loaded from the guest's /opt/firebird/SYSDBA.password, never printed).
# Writes raw evidence to /work/out, the .fbk to /work/backup and the restore to /work/restore.
# All of /work lives outside Git.
set -u
SRC=/work/db/legacy-copy.fdb
OUT=/work/out
FBK=/work/backup/legacy.fbk
RST=/work/restore/legacy-restored.fdb
SQL_DIR=$(dirname "$0")
mkdir -p "$OUT" /work/backup /work/restore

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$OUT/run.log"; }

counts() { # $1=db $2=out.tsv  (Firebird 1.5 has no TRIM / SET HEADING: use list mode)
  printf 'SET LIST ON;\nSELECT RDB$RELATION_NAME AS TBL FROM RDB$RELATIONS WHERE COALESCE(RDB$SYSTEM_FLAG,0)=0 AND RDB$VIEW_BLR IS NULL ORDER BY 1;\n' > /tmp/t.sql
  isql -q -i /tmp/t.sql "$1" | awk '$1=="TBL"{print $2}' > /tmp/tables.txt
  { echo "SET LIST ON;"; while read -r t; do echo "SELECT '$t' AS TBL, COUNT(*) AS N FROM \"$t\";"; done < /tmp/tables.txt; } > /tmp/c.sql
  isql -q -i /tmp/c.sql "$1" 2>&1 | awk '$1=="TBL"{t=$2;next} $1=="N"{print t"\t"$2;next} /Statement failed|error/{print "ERR\t"$0}' > "$2"
}

log "engine: $(isql -z </dev/null 2>&1 | head -1)"
log "isql binary: $(file -L /opt/firebird/bin/isql | cut -d: -f2 | cut -d, -f1-2)"
gstat -h "$SRC" > "$OUT/source-header.txt" 2>&1

log "catalog summary"
isql -q -i "$SQL_DIR/../db01_catalog.sql" "$SRC" > "$OUT/source-catalog.txt" 2>&1
log "DDL export"
isql -q -x "$SRC" > "$OUT/source-schema.sql" 2>"$OUT/source-schema.err"
log "per-table counts (source)"
counts "$SRC" "$OUT/source-counts.tsv"

log "gbak backup (transportable, no garbage collection)"
rm -f "$FBK" "$RST"
gbak -b -t -g -v -y "$OUT/gbak-backup.log" "$SRC" "$FBK"; log "gbak backup rc=$?"
log "gbak restore to separate database"
gbak -c -v -y "$OUT/gbak-restore.log" "$FBK" "$RST"; log "gbak restore rc=$?"
gstat -h "$RST" > "$OUT/restored-header.txt" 2>&1

log "DDL export + counts (restored)"
isql -q -x "$RST" > "$OUT/restored-schema.sql" 2>"$OUT/restored-schema.err"
counts "$RST" "$OUT/restored-counts.tsv"

# Compare: ignore the lines that name the database file path (isql "Database:" header, CREATE DATABASE).
grep -v -e '^Database:' -e '^CREATE DATABASE' -e '^/\* CREATE DATABASE' "$OUT/source-schema.sql" > /tmp/a.sql
grep -v -e '^Database:' -e '^CREATE DATABASE' -e '^/\* CREATE DATABASE' "$OUT/restored-schema.sql" > /tmp/b.sql
if diff /tmp/a.sql /tmp/b.sql > "$OUT/schema.diff"; then SCHEMA=match; else SCHEMA=DIFF; fi
if diff "$OUT/source-counts.tsv" "$OUT/restored-counts.tsv" > "$OUT/counts.diff"; then COUNTS=match; else COUNTS=DIFF; fi
{
  echo "source_tables=$(grep -vc '^ERR' "$OUT/source-counts.tsv")"
  echo "source_rows_total=$(awk -F'\t' '$1!="ERR"{s+=$2}END{print s}' "$OUT/source-counts.tsv")"
  echo "count_errors=$(grep -c '^ERR' "$OUT/source-counts.tsv")"
  echo "restored_tables=$(grep -vc '^ERR' "$OUT/restored-counts.tsv")"
  echo "restored_rows_total=$(awk -F'\t' '$1!="ERR"{s+=$2}END{print s}' "$OUT/restored-counts.tsv")"
  echo "schema_ddl_lines=$(wc -l < /tmp/a.sql)"
  echo "schema_compare=$SCHEMA"
  echo "counts_compare=$COUNTS"
  echo "fbk_bytes=$(stat -c %s "$FBK" 2>/dev/null)"
} | tee "$OUT/compare.txt"
