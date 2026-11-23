# -*- coding: utf-8 -*-
"""DB-04 · chunked, allowlisted export of the legacy Firebird snapshot with a manifest.

Runs INSIDE the Firebird 1.5.6 i386 guest image (fb156cs-py: Python 3.5 + fdb 2.0.1), so it
avoids f-strings and other 3.6+ syntax. Usage:

    python3 db04_export.py --db /work/restore/legacy-restored.fdb --out /work/extracts/run-a \
        --as-of 2026-11-23 --snapshot-sha256 <legacy.fbk sha256> --original-sha256 <FDB sha256>

Rules (recorded in the manifest):
* Connection charset WIN1252: the server transliterates column data to WIN1252 and the
  driver decodes it strictly; output files are UTF-8. A byte that WIN1252 cannot decode aborts.
* NULL is written as \\N (unquoted). Empty strings stay "" (quoted by csv when needed).
* NUMERIC/DECIMAL are cast to text by the server (CAST AS VARCHAR(40)), which prints exactly the
  declared scale (NUMERIC(6,4) 1 -> 1.0000) with no float round-trip. FLOAT (32-bit) and
  DOUBLE are written with repr() and typed float32/float64 in the manifest.
* DATE -> YYYY-MM-DD, TIME -> HH:MM:SS.ffffff, TIMESTAMP -> YYYY-MM-DDTHH:MM:SS.ffffff (no timezone:
  source values are local wall-clock). Values are written as stored, including future dates.
* CHAR values keep their space padding (no trimming at extract time).
* Rows are ordered by the table's order key (ID) and split into fixed-size chunks.
* Everything is read in ONE read-only snapshot transaction. manifest.json is written last
  (atomic rename), so an interrupted export has no manifest and is rejected.
"""
from __future__ import print_function

import argparse
import csv
import ctypes
import datetime
import decimal
import hashlib
import io
import json
import os
import sys

NULL = "\\N"
FORMAT_VERSION = 1


# --- fdb on Firebird 1.5: provide fb_interpret (2.0+) via isc_interprete --------------------
def _patch_fdb_for_fb15():
    import fdb.ibase as ib

    real_cdll = ib.CDLL

    def cdll(name, *a, **k):
        lib = real_cdll(name, *a, **k)
        if not hasattr(lib, "fb_interpret"):
            raw = lib._FuncPtr(("isc_interprete", lib))
            raw.restype = ctypes.c_int
            raw.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.POINTER(ib.ISC_STATUS))]

            def fb_interpret(buf, size, pvector):
                return raw(buf, pvector)

            lib.fb_interpret = fb_interpret
        return lib

    ib.CDLL = cdll


_patch_fdb_for_fb15()
import fdb  # noqa: E402

fdb.load_api("/opt/firebird/lib/libfbembed.so")

TYPE_NAMES = {7: "smallint", 8: "integer", 16: "bigint", 10: "float32", 27: "float64",
              12: "date", 13: "time", 35: "timestamp", 14: "char", 37: "varchar", 261: "blob"}


def column_meta(cur, table):
    # System names are CHAR(31) UNICODE_FSS; fdb sizes them as 31/3 chars under a WIN1252
    # connection and truncates them, so cast them to WIN1252 explicitly.
    cur.execute(
        "SELECT CAST(rf.RDB$FIELD_NAME AS VARCHAR(31) CHARACTER SET WIN1252), f.RDB$FIELD_TYPE, "
        "f.RDB$FIELD_SCALE, f.RDB$FIELD_LENGTH, f.RDB$CHARACTER_LENGTH, "
        "CAST(cs.RDB$CHARACTER_SET_NAME AS VARCHAR(31) CHARACTER SET WIN1252), rf.RDB$NULL_FLAG, f.RDB$NULL_FLAG "
        "FROM RDB$RELATION_FIELDS rf JOIN RDB$FIELDS f ON f.RDB$FIELD_NAME = rf.RDB$FIELD_SOURCE "
        "LEFT JOIN RDB$CHARACTER_SETS cs ON cs.RDB$CHARACTER_SET_ID = f.RDB$CHARACTER_SET_ID "
        "WHERE rf.RDB$RELATION_NAME = ? ORDER BY rf.RDB$FIELD_POSITION", (table,))
    meta = {}
    for name, ftype, scale, length, charlen, cs, nn1, nn2 in cur.fetchall():
        name = name.strip()
        t = TYPE_NAMES.get(ftype, "type%d" % ftype)
        m = {"type": t, "nullable": not (nn1 or nn2)}
        if ftype in (7, 8, 16) and scale and scale < 0:
            m["type"] = "decimal"
            m["scale"] = -scale
        if ftype in (14, 37):
            m["length"] = charlen or length
            m["charset"] = (cs or "NONE").strip()
        meta[name] = m
    return meta


def decimal_formatter(scale):
    """Decimals are cast to text by Firebird (CAST(col AS VARCHAR(40))), which prints exactly
    the declared scale; this only checks the shape (cheap under emulation)."""
    def f(v):
        if v is None:
            return NULL
        v = v.strip()
        if scale and (len(v) <= scale or v[-scale - 1] != "."):
            raise ValueError("decimal %r does not carry declared scale %d" % (v, scale))
        return v
    return f


def column_formatter(m):
    """Per-column formatter chosen once from the catalog type (avoids per-value type tests)."""
    t = m["type"]
    if t == "decimal":
        return decimal_formatter(m["scale"])
    if t in ("smallint", "integer", "bigint"):
        return lambda v: NULL if v is None else str(v)
    if t in ("char", "varchar"):
        return lambda v: NULL if v is None else v
    if t in ("float32", "float64"):
        return lambda v: NULL if v is None else repr(v)
    return fmt


def fmt(v):
    if v is None:
        return NULL
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, decimal.Decimal):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, datetime.datetime):
        return v.strftime("%Y-%m-%dT%H:%M:%S.%f")
    if isinstance(v, datetime.date):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, datetime.time):
        return v.strftime("%H:%M:%S.%f")
    return str(v)


class ChunkWriter(object):
    def __init__(self, out_dir, table, columns, chunk_rows, formatters):
        self.dir = os.path.join(out_dir, table)
        os.makedirs(self.dir)
        self.table, self.columns, self.chunk_rows = table, columns, chunk_rows
        self.formatters = formatters
        self.chunks, self.raw, self.n = [], None, 0
        self.key_hash = hashlib.sha256()

    def _open(self):
        name = "part-%05d.csv" % (len(self.chunks) + 1)
        self.cur = {"file": "%s/%s" % (self.table, name), "rows": 0, "first_key": None, "last_key": None}
        self.raw = io.open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="")
        self.w = csv.writer(self.raw, lineterminator="\n")
        self.w.writerow(self.columns)

    def _close(self):
        self.raw.close()
        path = os.path.join(self.dir, os.path.basename(self.cur["file"]))
        with open(path, "rb") as f:
            data = f.read()
        self.cur["sha256"] = hashlib.sha256(data).hexdigest()
        self.cur["bytes"] = len(data)
        self.chunks.append(self.cur)
        self.raw = None

    def write(self, key, row):
        if self.raw is None:
            self._open()
        self.w.writerow([f(v) for f, v in zip(self.formatters, row)])
        self.cur["rows"] += 1
        self.n += 1
        if self.cur["first_key"] is None:
            self.cur["first_key"] = key
        self.cur["last_key"] = key
        self.key_hash.update(("%s\n" % key).encode("ascii"))
        if self.cur["rows"] >= self.chunk_rows:
            self._close()

    def finish(self):
        if self.raw is None and not self.chunks:
            self._open()  # header-only chunk proves an empty table
        if self.raw is not None:
            self._close()
        return self.chunks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--allowlist", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "allowlist.json"))
    ap.add_argument("--as-of", required=True, help="snapshot date; later dates are flagged, not dropped")
    ap.add_argument("--snapshot-sha256", required=True, help="sha256 of the immutable .fbk snapshot")
    ap.add_argument("--original-sha256", required=True, help="sha256 of the original legacy .FDB")
    ap.add_argument("--chunk-rows", type=int, default=None)
    args = ap.parse_args()

    if os.path.exists(args.out):
        sys.exit("refusing to overwrite existing output dir: %s" % args.out)
    os.makedirs(args.out)
    with open(args.allowlist, "rb") as f:
        allow_bytes = f.read()
    allow = json.loads(allow_bytes.decode("utf-8"))
    chunk_rows = args.chunk_rows or allow["chunk_rows"]
    as_of = datetime.datetime.strptime(args.as_of, "%Y-%m-%d").date()

    con = fdb.connect(database=args.db, user=os.environ["ISC_USER"], password=os.environ["ISC_PASSWORD"],
                      charset="WIN1252")
    tpb = fdb.TPB()
    tpb.access_mode = fdb.isc_tpb_read
    tpb.isolation_level = fdb.isc_tpb_concurrency  # snapshot
    con.begin(tpb=tpb.render())
    cur = con.cursor()

    cur.execute("SELECT CAST(RDB$CHARACTER_SET_NAME AS VARCHAR(31) CHARACTER SET WIN1252) FROM RDB$DATABASE")
    db_charset = cur.fetchone()[0].strip()
    cur.execute("SELECT I_LOJA FROM CONFIGURACOES")
    branches = sorted(r[0] for r in cur.fetchall())
    if len(branches) != 1:
        sys.exit("expected exactly one CONFIGURACOES.I_LOJA, got %r" % branches)
    instance = "estoquefacil-fb15/%d" % branches[0]

    tables = {}
    nf_numbers = {}
    for table in sorted(allow["tables"]):
        spec = allow["tables"][table]
        cols = spec["columns"]
        okey = spec.get("order_key", allow["order_key"])
        meta = column_meta(cur, table)
        if not meta:
            sys.exit("allowlisted table not found: %s" % table)
        missing = [c for c in cols if c not in meta]
        if missing:
            sys.exit("allowlisted columns not found in %s: %s" % (table, missing))
        multibyte = [c for c in cols if meta[c].get("charset") not in (None, "WIN1252", "NONE")]
        if multibyte:
            sys.exit("%s: non-WIN1252 text columns would be mis-sized by the driver: %s" % (table, multibyte))
        cur.execute('SELECT COUNT(*) FROM "%s"' % table)
        expected = cur.fetchone()[0]
        kidx = cols.index(okey)
        formatters = [column_formatter(meta[c]) for c in cols]
        w = ChunkWriter(args.out, table, cols, chunk_rows, formatters)
        select = ", ".join('CAST("%s" AS VARCHAR(40))' % c if meta[c]["type"] == "decimal" else '"%s"' % c for c in cols)
        cur.execute('SELECT %s FROM "%s" ORDER BY "%s"' % (select, table, okey))
        prev = None
        for row in cur:
            key = row[kidx]
            if prev is not None and not key > prev:
                sys.exit("%s: order key not strictly increasing at %r" % (table, key))
            prev = key
            w.write(key, row)
            if table == "NOTAS_FISCAIS":
                k = (row[cols.index("S_TIPO")], row[cols.index("NUMERO")])
                nf_numbers[k] = nf_numbers.get(k, 0) + 1
        chunks = w.finish()
        if w.n != expected:
            sys.exit("%s: wrote %d rows but COUNT(*) is %d" % (table, w.n, expected))
        tables[table] = {
            "order_key": okey,
            "columns": [dict([("name", c)] + sorted(meta[c].items())) for c in cols],
            "row_count": w.n,
            "key_digest": w.key_hash.hexdigest(),
            "chunks": chunks,
        }
        print("%-24s %8d rows %3d chunk(s)" % (table, w.n, len(chunks)))

    def scalar(sql, params=()):
        cur.execute(sql, params)
        return cur.fetchone()[0]

    future_mov = {}
    cur.execute("SELECT S_OPERACAO, COUNT(*), MAX(D_DATA) FROM ENTRADAS_SAIDAS WHERE D_DATA > ? GROUP BY S_OPERACAO", (as_of,))
    for op, n, mx in cur.fetchall():
        future_mov[op] = {"rows": n, "max_date": fmt(mx)}
    quality = {
        "nf_lines_missing_product": {
            "rows": scalar("SELECT COUNT(*) FROM ITENS_NOTA_FISCAL i WHERE NOT EXISTS (SELECT 1 FROM PRODUTOS p WHERE p.ID = i.ID_PRODUTO)"),
            "distinct_product_ids": scalar("SELECT COUNT(DISTINCT ID_PRODUTO) FROM ITENS_NOTA_FISCAL i WHERE NOT EXISTS (SELECT 1 FROM PRODUTOS p WHERE p.ID = i.ID_PRODUTO)"),
            "policy": "kept verbatim with their source ID_PRODUTO; not dropped or remapped. Flag downstream (DB-05/DB-09).",
        },
        "nf_reused_numbers": {
            "numbers_reused_within_type": sum(1 for v in nf_numbers.values() if v > 1),
            "headers_on_reused_numbers": sum(v for v in nf_numbers.values() if v > 1),
            "policy": "kept as separate documents keyed by NOTAS_FISCAIS.ID (DB-03); never merged on number.",
        },
        "movements_after_as_of": {
            "as_of": args.as_of,
            "by_operation": future_mov,
            "policy": "kept with their stored D_DATA; flagged as after the snapshot date, not shifted or dropped.",
        },
        "nf_after_as_of": scalar("SELECT COUNT(*) FROM NOTAS_FISCAIS WHERE DATA_EMISSAO > ?", (as_of,)),
        "sales_qty_le_zero": scalar("SELECT COUNT(*) FROM ENTRADAS_SAIDAS WHERE S_OPERACAO = 'V' AND F_QUANTIDADE <= 0"),
    }
    con.commit()
    con.close()

    manifest = {
        "format_version": FORMAT_VERSION,
        "card": "DB-04",
        "source": {
            "system": "Firebird 1.5.6 Classic (LI-V1.5.6.5026) i386, read via fdb 2.0.1",
            "ods": "10.1", "dialect": 3, "db_charset": db_charset,
            "original_fdb_sha256": args.original_sha256,
            "snapshot_fbk_sha256": args.snapshot_sha256,
            "snapshot_note": "the restore is a working copy of the .fbk; attaching updates its header, so the .fbk hash identifies the snapshot",
        },
        "scope": {"instance": instance, "company": "single (CONFIGURACOES)", "branch": branches[0],
                  "warehouse_key": "%s/local/%d" % (instance, branches[0]), "as_of": args.as_of},
        "rules": {
            "file_encoding": "utf-8", "source_charset": "WIN1252 (connection charset, strict decode)",
            "csv": "RFC 4180, comma, '\\n' line end, header row", "null": NULL,
            "decimal": "fixed-point text with exactly the declared scale; no rounding", "float": "repr(); typed float32/float64",
            "date": "YYYY-MM-DD", "time": "HH:MM:SS.ffffff", "timestamp": "YYYY-MM-DDTHH:MM:SS.ffffff (local, no tz)",
            "char": "space padding preserved", "order": "by order_key ascending, strictly increasing",
            "chunk_rows": chunk_rows,
        },
        "allowlist_sha256": hashlib.sha256(allow_bytes).hexdigest(),
        "tables": tables,
        "quality": quality,
        "unresolved": [
            "ENTRADAS_SAIDAS.S_OPERACAO meanings are inferred (V sale, C entry, A adjustment; P, D and _ unknown); TIPOS_ENTRADAS_SAIDAS is empty.",
            "ENTRADAS_SAIDAS rows behave like daily per-product totals (all I_PDV = 1); ticket-level sales are in VENDEDORES_VENDAS / ITENS_CLIENTE_COMPRA.",
            "NOTAS_FISCAIS.S_TIPO 'A' vs 'E' business meaning is not documented in the source.",
            "ITENS_NOTA_FISCAL.QUANTIDADE is declared NUMERIC(6,4) but holds values up to 13020; exported exactly as stored.",
            "NOTAS_FISCAIS.QUANTIDADE holds the line count, not units (DB-03).",
        ],
        "run": {"extracted_at_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "db_path": args.db},
    }
    tmp = os.path.join(args.out, "manifest.json.tmp")
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False))
    os.rename(tmp, os.path.join(args.out, "manifest.json"))
    print("manifest written:", os.path.join(args.out, "manifest.json"))


if __name__ == "__main__":
    main()
