#!/bin/sh
# DB-03 · runs INSIDE the Firebird 1.5.6 i386 container (see fb156cs/). Reads the validated
# restore and writes key-column TSVs to /work/out/db03 (outside Git). Credentials come from
# the guest env (ISC_USER/ISC_PASSWORD) and are never printed.
set -eu
DB=${DB03_SOURCE_DB:-/work/restore/legacy-restored.fdb}
OUT=/work/out/db03
DIR=$(dirname "$0")
mkdir -p "$OUT"
isql -q -i "$DIR/db03_profile.sql" -e "$DB" > "$OUT/profile.txt" 2>&1 || true
isql -q -i "$DIR/db03_join_check.sql" "$DB" > "$OUT/join_check.txt" 2>&1
isql -q -i "$DIR/db03_export_keys.sql" "$DB" > "$OUT/keys.raw" 2>"$OUT/keys.err"
for tag in NF NFI ES ICC SP ISP PR FO CF SL TE PE LJ; do
  grep "^$tag|" "$OUT/keys.raw" | sed "s/^$tag|//; s/[[:space:]]*\$//" | tr '|' '\t' > "$OUT/$tag.tsv"
done
rm -f "$OUT/keys.raw"
wc -l "$OUT"/*.tsv
