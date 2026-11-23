#!/usr/bin/env bash
# DB-01 · Open and fingerprint the legacy Firebird database (disposable copies only).
#
# Usage:
#   LEGACY_FDB=/path/to/original.fdb LEGACY_WORK=~/.estoquefacil-legacy-work \
#     FIREBIRD_PASSWORD=... backend/legacy/firebird/db01_fingerprint.sh
#
# - The original file is only read (hashed + copied). Engine access happens on copies in
#   $LEGACY_WORK/db inside an isolated linux/amd64 Firebird 2.5 container (--network none).
#   Firebird 3+ cannot open ODS < 12, so 2.5 is the newest engine able to try ODS 10.x.
# - Outputs go to $LEGACY_WORK/out and must stay outside Git. FIREBIRD_PASSWORD is only the
#   throwaway container's SYSDBA password.
# - Exit 0: catalog readable (DDL + aggregate counts exported).
#   Exit 2: engine rejected the file; evidence captured in out/blocker.txt.
set -uo pipefail

: "${LEGACY_FDB:?set LEGACY_FDB to the original .fdb path}"
: "${FIREBIRD_PASSWORD:?set FIREBIRD_PASSWORD (local SYSDBA password for the container)}"
WORK="${LEGACY_WORK:-$HOME/.estoquefacil-legacy-work}"
IMAGE="${FIREBIRD_IMAGE:-jacobalberty/firebird:2.5-ss}"
NAME="${FIREBIRD_CONTAINER:-fb25-legacy}"
SQL_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$WORK/out"
mkdir -p "$WORK/db" "$OUT"
COPY="$WORK/db/legacy-copy.fdb"

hash_of() { shasum -a 256 "$1" | awk '{print $1}'; }
ORIG_BEFORE="$(hash_of "$LEGACY_FDB")"
[ -f "$COPY" ] || cp "$LEGACY_FDB" "$COPY"

if ! docker inspect "$NAME" >/dev/null 2>&1; then
  docker run -d --name "$NAME" --platform linux/amd64 --network none \
    -e ISC_PASSWORD="$FIREBIRD_PASSWORD" -v "$WORK/db:/firebird/data" "$IMAGE" >/dev/null
  sleep 8
fi
docker exec "$NAME" sh -c 'chmod 777 /firebird/data; chmod 666 /firebird/data/legacy-copy.fdb'

fb() { docker exec -i -e ISC_USER=SYSDBA "$NAME" "/usr/local/firebird/bin/$1" "${@:2}"; }
DB=localhost:/firebird/data/legacy-copy.fdb

{ docker exec "$NAME" uname -m; fb isql -z </dev/null 2>&1 | head -1; } > "$OUT/engine.txt"
fb gstat -h /firebird/data/legacy-copy.fdb > "$OUT/header.txt" 2>&1
fb isql -q "$DB" < "$SQL_DIR/db01_catalog.sql" > "$OUT/catalog-summary.txt" 2>&1
OPEN_RC=$?

finish() {
  ORIG_AFTER="$(hash_of "$LEGACY_FDB")"
  {
    echo "original_sha256_before=$ORIG_BEFORE"
    echo "original_sha256_after=$ORIG_AFTER"
    echo "original_unchanged=$([ "$ORIG_BEFORE" = "$ORIG_AFTER" ] && echo yes || echo NO)"
    echo "copy_sha256_after_open=$(hash_of "$COPY")"
    echo "image=$IMAGE"
    echo "image_digest=$(docker image inspect --format '{{index .RepoDigests 0}}' "$IMAGE")"
    echo "catalog_readable=$1"
  } > "$OUT/fingerprint.txt"
  cat "$OUT/fingerprint.txt"
  [ "$ORIG_BEFORE" = "$ORIG_AFTER" ] || exit 3
  exit "$2"
}

if [ $OPEN_RC -ne 0 ]; then
  # Diagnostic: is the header's implementation class the only incompatibility?
  # Patch hdr_implementation (offset 60) on a second throwaway copy to this engine's class.
  docker exec "$NAME" sh -c '
    cd /firebird/data && rm -f probe.fdb legacy-copy-impl.fdb
    echo "CREATE DATABASE '\''localhost:/firebird/data/probe.fdb'\'';" | ISC_USER=SYSDBA /usr/local/firebird/bin/isql -q
    CLS=$(/usr/local/firebird/bin/gstat -h probe.fdb | awk "/Implementation ID/{print \$3}")
    cp legacy-copy.fdb legacy-copy-impl.fdb && chmod 666 legacy-copy-impl.fdb
    printf "\\$(printf %o "$CLS")" | dd of=legacy-copy-impl.fdb bs=1 seek=60 count=1 conv=notrunc 2>/dev/null
    echo "engine_native_implementation_id=$CLS"
    echo "SELECT COUNT(*) FROM RDB\$RELATIONS;" | ISC_USER=SYSDBA /usr/local/firebird/bin/isql -q localhost:/firebird/data/legacy-copy-impl.fdb 2>&1
    rm -f probe.fdb legacy-copy-impl.fdb' > "$OUT/impl-class-probe.txt" 2>&1
  {
    echo "DB-01 blocker: engine rejected the disposable copy"
    echo "engine: $(tr '\n' ' ' < "$OUT/engine.txt")"
    grep -E "ODS version|Implementation ID|Database dialect|Creation date|Page size" "$OUT/header.txt"
    echo "open error (unmodified copy):"; sed 's/^/  /' "$OUT/catalog-summary.txt"
    echo "probe with header class patched to native (second throwaway copy):"; sed 's/^/  /' "$OUT/impl-class-probe.txt"
  } > "$OUT/blocker.txt"
  cat "$OUT/blocker.txt"
  finish no 2
fi

fb isql -q -x "$DB" > "$OUT/schema.sql" 2>"$OUT/schema-export.err"
fb isql -q "$DB" > "$OUT/tables.txt" 2>&1 <<'SQL'
SET HEADING OFF;
SELECT TRIM(RDB$RELATION_NAME) FROM RDB$RELATIONS
 WHERE COALESCE(RDB$SYSTEM_FLAG,0)=0 AND RDB$VIEW_BLR IS NULL ORDER BY 1;
SQL
{
  echo "SET HEADING OFF;"
  grep -v '^[[:space:]]*$' "$OUT/tables.txt" | while read -r t; do
    echo "SELECT '$t', COUNT(*) FROM \"$t\";"
  done
} > "$OUT/counts.sql"
fb isql -q "$DB" < "$OUT/counts.sql" | awk 'NF==2{print $1"\t"$2}' > "$OUT/table-counts.tsv"
finish yes 0
