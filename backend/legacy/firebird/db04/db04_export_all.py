# -*- coding: utf-8 -*-
"""DB-04 follow-up · COMPLETE read-only export of every user table of the legacy Firebird snapshot.

Runs INSIDE the Firebird 1.5.6 i386 guest image (fb156cs-py: Python 3.5 + fdb 2.0.1), like
``db04_export.py`` whose helpers it reuses. It is NOT the allowlisted extract that the importers read:
it exports every table and every column, including personal data and credentials, so its output stays
on the local disk with owner-only permissions and outside Git.

    python3 db04_export_all.py --db /work/restore/legacy-restored.fdb --out /work/extracts/full-a \
        --meta /work/extracts/full-a-meta --reference-counts /work/out/source-counts.tsv \
        --as-of 2026-11-23 --snapshot-sha256 <fbk sha256> --original-sha256 <FDB sha256>

Rules
* Everything is read in ONE read-only snapshot transaction. Nothing is written to the database.
* Same file format as DB-04 (UTF-8 CSV, ``\\N`` for NULL, exact decimals, chunked, sha256 per chunk), so
  ``python -m legacy.manifest validate`` accepts the result.
* Order key: the primary key when it is a single integer column, else a synthetic ``__ROW`` counter
  in ``RDB$DB_KEY`` order (recorded as ``synthetic_key`` in the manifest).
* BLOB columns are written as hex. COMPUTED BY decimals are typed ``computed_decimal`` (exact server text,
  no fixed-scale check: the catalog scale is not the scale of the expression). Text columns in UNICODE_FSS are cast to WIN1252 by the server.
* ``--lenient-decode``: bytes that cp1252 leaves undefined map to the code point of the same value (counted per
  table as ``lenient_decoded_bytes``). Used only to re-export a table that failed the strict decode.
* A table that cannot be exported is removed, logged in ``errors.log`` and listed in ``errors`` of the
  manifest; the other tables continue. The manifest says ``complete: false`` in that case.
* ``counts.tsv`` compares, per table: COUNT(*) in the same transaction, rows written and the count
  recorded by DB-01 on the original copy.
"""
from __future__ import print_function

import argparse
import binascii
import datetime
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db04_export as base  # noqa: E402

import codecs  # noqa: E402

fdb = base.fdb
NULL = base.NULL
LENIENT_BYTES = [0]


def _lenient_decode(data, errors="strict"):
    """cp1252, except that the five bytes it leaves undefined (0x81 0x8d 0x8f 0x90 0x9d) map to the code point
    of the same value, so nothing is lost or guessed. Counted in LENIENT_BYTES."""
    out = []
    for b in bytearray(data):
        try:
            out.append(bytes(bytearray([b])).decode("cp1252"))
        except UnicodeDecodeError:
            out.append(chr(b))
            LENIENT_BYTES[0] += 1
    return "".join(out), len(data)


def enable_lenient_decode():
    cp = codecs.lookup("cp1252")
    codecs.register(lambda name: codecs.CodecInfo(cp.encode, _lenient_decode, name="cp1252_lenient")
                    if name == "cp1252_lenient" else None)
    import fdb.fbcore as fbcore
    for mod in (fbcore, fdb.ibase):
        mapping = getattr(mod, "DB_CHAR_SET_NAME_TO_PYTHON_ENCODING_MAP", None)
        if mapping is not None:
            mapping["WIN1252"] = "cp1252_lenient"
INTEGER_TYPES = ("smallint", "integer", "bigint")


def list_tables(cur):
    cur.execute("SELECT CAST(RDB$RELATION_NAME AS VARCHAR(31) CHARACTER SET WIN1252) FROM RDB$RELATIONS "
                "WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0 AND RDB$VIEW_SOURCE IS NULL ORDER BY 1")
    return [r[0].strip() for r in cur.fetchall()]


def ordered_columns(cur, table):
    cur.execute("SELECT CAST(rf.RDB$FIELD_NAME AS VARCHAR(31) CHARACTER SET WIN1252) FROM RDB$RELATION_FIELDS rf "
                "WHERE rf.RDB$RELATION_NAME = ? ORDER BY rf.RDB$FIELD_POSITION", (table,))
    return [r[0].strip() for r in cur.fetchall()]


def primary_key(cur, table):
    cur.execute("SELECT CAST(s.RDB$FIELD_NAME AS VARCHAR(31) CHARACTER SET WIN1252) FROM RDB$RELATION_CONSTRAINTS rc "
                "JOIN RDB$INDEX_SEGMENTS s ON s.RDB$INDEX_NAME = rc.RDB$INDEX_NAME "
                "WHERE rc.RDB$RELATION_NAME = ? AND rc.RDB$CONSTRAINT_TYPE = 'PRIMARY KEY' "
                "ORDER BY s.RDB$FIELD_POSITION", (table,))
    return [r[0].strip() for r in cur.fetchall()]


def computed_columns(cur, table):
    """COMPUTED BY columns: the catalog scale is not the scale of the expression's result."""
    cur.execute("SELECT CAST(rf.RDB$FIELD_NAME AS VARCHAR(31) CHARACTER SET WIN1252) FROM RDB$RELATION_FIELDS rf "
                "JOIN RDB$FIELDS f ON f.RDB$FIELD_NAME = rf.RDB$FIELD_SOURCE "
                "WHERE rf.RDB$RELATION_NAME = ? AND f.RDB$COMPUTED_BLR IS NOT NULL", (table,))
    return set(r[0].strip() for r in cur.fetchall())


def computed_decimal_formatter(v):
    return NULL if v is None else v.strip()


def blob_formatter(v):
    if v is None:
        return NULL
    if hasattr(v, "read"):
        v = v.read()
    if not isinstance(v, bytes):
        v = v.encode("cp1252", "replace")
    return binascii.hexlify(v).decode("ascii")


def select_expr(col, m):
    """Text columns that are not WIN1252 are cast by the server (the driver would mis-size them)."""
    if m["type"] in ("char", "varchar") and m.get("charset") not in (None, "WIN1252", "NONE"):
        kind = "CHAR" if m["type"] == "char" else "VARCHAR"
        return 'CAST("%s" AS %s(%d) CHARACTER SET WIN1252)' % (col, kind, m["length"])
    if m["type"] in ("decimal", "computed_decimal"):
        return 'CAST("%s" AS VARCHAR(40))' % col
    return '"%s"' % col


def read_reference(path):
    ref = {}
    if path and os.path.isfile(path):
        with open(path) as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 2:
                    ref[parts[0]] = int(parts[1])
    return ref


def export_table(cur, out_dir, table, chunk_rows):
    cols = ordered_columns(cur, table)
    meta = base.column_meta(cur, table)
    missing = [c for c in cols if c not in meta]
    if not cols or missing:
        raise RuntimeError("catalog columns not resolvable: %s" % missing)
    for c in computed_columns(cur, table):
        if meta[c]["type"] == "decimal":
            meta[c] = dict(meta[c], type="computed_decimal", declared_scale=meta[c]["scale"])
            del meta[c]["scale"]
    pk = primary_key(cur, table)
    synthetic = not (len(pk) == 1 and meta[pk[0]]["type"] in INTEGER_TYPES)
    cur.execute('SELECT COUNT(*) FROM "%s"' % table)
    expected = cur.fetchone()[0]

    special = {"blob": blob_formatter, "computed_decimal": computed_decimal_formatter}
    formatters = [special.get(meta[c]["type"]) or base.column_formatter(meta[c]) for c in cols]
    names = list(cols)
    if synthetic:
        names = ["__ROW"] + names
        formatters = [lambda v: str(v)] + formatters
        order_key, order_by = "__ROW", "RDB$DB_KEY"
    else:
        order_key, order_by = pk[0], '"%s"' % pk[0]
    kidx = names.index(order_key)
    w = base.ChunkWriter(out_dir, table, names, chunk_rows, formatters)
    cur.execute("SELECT %s FROM \"%s\" ORDER BY %s" % (", ".join(select_expr(c, meta[c]) for c in cols), table, order_by))
    prev, n = None, 0
    for row in cur:
        n += 1
        if synthetic:
            key, row = n, (n,) + tuple(row)
        else:
            key = row[kidx]
            if prev is not None and not key > prev:
                raise RuntimeError("order key not strictly increasing")
            prev = key
        w.write(key, row)
    chunks = w.finish()
    if w.n != expected:
        raise RuntimeError("wrote %d rows but COUNT(*) is %d" % (w.n, expected))
    columns = [dict([("name", c)] + sorted(meta[c].items())) for c in cols]
    if synthetic:
        columns.insert(0, {"name": "__ROW", "type": "integer", "nullable": False, "synthetic": True})
    return {"order_key": order_key, "synthetic_key": synthetic, "columns": columns, "row_count": w.n,
            "key_digest": w.key_hash.hexdigest(), "chunks": chunks}, expected


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--meta", required=True, help="directory for counts.tsv and errors.log (outside the extract)")
    ap.add_argument("--reference-counts", default=None, help="DB-01 per-table counts (table<TAB>rows)")
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--snapshot-sha256", required=True)
    ap.add_argument("--original-sha256", required=True)
    ap.add_argument("--chunk-rows", type=int, default=100000)
    ap.add_argument("--only", default=None, help="comma-separated table names (testing, or re-exporting a failed table)")
    ap.add_argument("--lenient-decode", action="store_true",
                    help="map bytes that cp1252 leaves undefined to the same code point instead of aborting the table")
    args = ap.parse_args()
    for d in (args.out, args.meta):
        if os.path.exists(d):
            sys.exit("refusing to overwrite existing directory: %s" % d)
    os.makedirs(args.out)
    os.makedirs(args.meta)

    if args.lenient_decode:
        enable_lenient_decode()
    con = fdb.connect(database=args.db, user=os.environ["ISC_USER"], password=os.environ["ISC_PASSWORD"], charset="WIN1252")
    tpb = fdb.TPB()
    tpb.access_mode = fdb.isc_tpb_read
    tpb.isolation_level = fdb.isc_tpb_concurrency
    con.begin(tpb=tpb.render())
    cur = con.cursor()
    cur.execute("SELECT CAST(RDB$CHARACTER_SET_NAME AS VARCHAR(31) CHARACTER SET WIN1252) FROM RDB$DATABASE")
    db_charset = cur.fetchone()[0].strip()
    cur.execute("SELECT I_LOJA FROM CONFIGURACOES")
    branches = sorted(r[0] for r in cur.fetchall())
    instance = "estoquefacil-fb15/%d" % branches[0]

    reference = read_reference(args.reference_counts)
    tables = list_tables(cur)
    if args.only:
        tables = [t for t in tables if t in args.only.split(",")]
    manifest_tables, errors, counts = {}, [], []
    for i, table in enumerate(tables, 1):
        try:
            before = LENIENT_BYTES[0]
            entry, source_rows = export_table(cur, args.out, table, args.chunk_rows)
            if LENIENT_BYTES[0] != before:
                entry["lenient_decoded_bytes"] = LENIENT_BYTES[0] - before
            manifest_tables[table] = entry
            counts.append((table, source_rows, entry["row_count"], reference.get(table)))
            print("%3d/%d %-34s %9d rows %3d chunk(s)%s" % (i, len(tables), table, entry["row_count"], len(entry["chunks"]),
                                                          "  [synthetic key]" if entry["synthetic_key"] else ""))
        except Exception as e:  # noqa: BLE001 - one bad table must not stop the others
            shutil.rmtree(os.path.join(args.out, table), ignore_errors=True)
            errors.append({"table": table, "error": type(e).__name__, "detail": str(e)[:200]})
            counts.append((table, None, None, reference.get(table)))
            print("%3d/%d %-34s ERROR %s" % (i, len(tables), table, type(e).__name__))
        sys.stdout.flush()
    con.commit()
    con.close()

    with open(os.path.join(args.meta, "counts.tsv"), "w") as f:
        f.write("table\tsource_count\texported_rows\tdb01_reference\tmatch\n")
        for table, src, exp, ref in counts:
            ok = src is not None and src == exp and (ref is None or ref == src)
            f.write("%s\t%s\t%s\t%s\t%s\n" % (table, "" if src is None else src, "" if exp is None else exp,
                                              "" if ref is None else ref, "ok" if ok else "MISMATCH"))
    with open(os.path.join(args.meta, "errors.log"), "w") as f:
        for e in errors:
            f.write(json.dumps(e, sort_keys=True) + "\n")

    manifest = {
        "format_version": base.FORMAT_VERSION,
        "card": "DB-04-full",
        "mode": "complete: every user table and column of the snapshot (contains personal data and credentials; local only)",
        "complete": not errors and len(manifest_tables) == len(tables),
        "source": {"system": "Firebird 1.5.6 Classic (LI-V1.5.6.5026) i386, read via fdb 2.0.1", "ods": "10.1", "dialect": 3,
                   "db_charset": db_charset, "original_fdb_sha256": args.original_sha256,
                   "snapshot_fbk_sha256": args.snapshot_sha256},
        "scope": {"instance": instance, "company": "single (CONFIGURACOES)", "branch": branches[0],
                  "warehouse_key": "%s/local/%d" % (instance, branches[0]), "as_of": args.as_of},
        "rules": {"file_encoding": "utf-8", "source_charset": "WIN1252 (connection charset, strict decode)",
                  "csv": "RFC 4180, comma, '\\n' line end, header row", "null": NULL,
                  "decimal": "fixed-point text with exactly the declared scale; no rounding", "float": "repr(); typed float32/float64",
                  "date": "YYYY-MM-DD", "time": "HH:MM:SS.ffffff", "timestamp": "YYYY-MM-DDTHH:MM:SS.ffffff (local, no tz)",
                  "blob": "hex", "char": "space padding preserved", "order": "by order_key ascending, strictly increasing",
                  "synthetic_key": "__ROW counts rows in RDB$DB_KEY order; it is not a source value",
                  "chunk_rows": args.chunk_rows},
        "tables": manifest_tables,
        "errors": errors,
        "run": {"extracted_at_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "db_path": args.db},
    }
    tmp = os.path.join(args.out, "manifest.json.tmp")
    with open(tmp, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    os.rename(tmp, os.path.join(args.out, "manifest.json"))
    print("manifest written: %d tables, %d errors, complete=%s" % (len(manifest_tables), len(errors), manifest["complete"]))


if __name__ == "__main__":
    main()
