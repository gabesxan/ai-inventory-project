"""DB-04 · validate a staged legacy extract against its manifest before anything loads it.

    PYTHONPATH=. python3 -m legacy.manifest validate <extract_dir>
    PYTHONPATH=. python3 -m legacy.manifest compare <extract_a> <extract_b>

``validate`` rejects a batch (exit 1) and names every offending file. It checks for a
missing manifest (an incomplete export), missing, changed or unexpected files, row counts per
chunk and table, header columns, strictly increasing order keys inside and across chunks,
the per-table key digest, and that every decimal value has exactly its declared scale. ``load_ready`` is the gate the importer (DB-02) must call.
``compare`` proves that two exports of the same snapshot yield the same ordered row keys.
Stdlib only.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

MANIFEST = "manifest.json"
SUPPORTED_FORMATS = {1}
csv.field_size_limit(10_000_000)


class ManifestError(Exception):
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("extract rejected:\n" + "\n".join("  - " + e for e in errors))


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _key(v: str, numeric: bool):
    return int(v) if numeric else v


def load_manifest(d: Path) -> dict:
    p = d / MANIFEST
    if not p.is_file():
        raise ManifestError([f"missing: {MANIFEST} (incomplete or unfinished export) in {d}"])
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ManifestError([f"unreadable: {MANIFEST} ({e})"])
    if m.get("format_version") not in SUPPORTED_FORMATS:
        raise ManifestError([f"unsupported format_version in {MANIFEST}: {m.get('format_version')!r}"])
    return m


def iter_rows(d: Path, table: str, m: dict) -> Iterator[List[str]]:
    for ch in m["tables"][table]["chunks"]:
        with (d / ch["file"]).open(encoding="utf-8", newline="") as f:
            r = csv.reader(f)
            next(r)
            yield from r


def ordered_keys(d: Path, table: str, m: dict) -> Iterator[str]:
    t = m["tables"][table]
    cols = [c["name"] for c in t["columns"]]
    i = cols.index(t["order_key"])
    for row in iter_rows(d, table, m):
        yield row[i]


def validate(d: Path) -> dict:
    d = Path(d)
    m = load_manifest(d)
    errors: List[str] = []
    listed = {MANIFEST}
    for table, t in sorted(m["tables"].items()):
        cols = [c["name"] for c in t["columns"]]
        if t["order_key"] not in cols:
            errors.append(f"{table}: order key {t['order_key']} not among columns")
            continue
        ki = cols.index(t["order_key"])
        dec = [(i, re.compile(r"^-?\d+\.\d{%d}$" % c["scale"] if c["scale"] else r"^-?\d+$"))
               for i, c in enumerate(t["columns"]) if c["type"] == "decimal"]
        numeric = next(c for c in t["columns"] if c["name"] == t["order_key"])["type"] in ("smallint", "integer", "bigint")
        total, prev, kh = 0, None, hashlib.sha256()
        for ch in t["chunks"]:
            rel = ch["file"]
            listed.add(rel)
            p = d / rel
            if not p.is_file():
                errors.append(f"missing: {rel}")
                continue
            if p.stat().st_size != ch["bytes"] or _sha256(p) != ch["sha256"]:
                errors.append(f"changed: {rel} (sha256/bytes differ from manifest)")
                continue
            n, first, last, broken = 0, None, None, False
            with p.open(encoding="utf-8", newline="") as f:
                r = csv.reader(f)
                header = next(r, None)
                if header != cols:
                    errors.append(f"header mismatch: {rel}")
                    continue
                for row in r:
                    if len(row) != len(cols):
                        errors.append(f"bad row width in {rel} at data row {n + 1}")
                        broken = True
                        break
                    bad = next((cols[i] for i, rx in dec if row[i] != "\\N" and not rx.match(row[i])), None)
                    if bad:
                        errors.append(f"decimal scale violated in {rel} column {bad} at key {row[ki]}")
                        broken = True
                        break
                    k = _key(row[ki], numeric)
                    if prev is not None and not k > prev:
                        errors.append(f"order key not increasing in {rel} at {row[ki]}")
                        broken = True
                        break
                    prev = k
                    first = row[ki] if first is None else first
                    last = row[ki]
                    kh.update(f"{row[ki]}\n".encode("ascii"))
                    n += 1
            if broken:
                total += ch["rows"]
                continue
            if n != ch["rows"]:
                errors.append(f"row count mismatch: {rel} has {n}, manifest says {ch['rows']}")
            if n and (str(ch["first_key"]) != first or str(ch["last_key"]) != last):
                errors.append(f"key range mismatch: {rel}")
            total += n
        if total != t["row_count"] and not any(table + "/" in e for e in errors):
            errors.append(f"{table}: {total} rows in chunks, manifest row_count {t['row_count']}")
        if kh.hexdigest() != t["key_digest"] and not any(table + "/" in e for e in errors):
            errors.append(f"{table}: key digest mismatch")
    for p in sorted(d.rglob("*")):
        rel = p.relative_to(d).as_posix()
        if p.is_file() and rel not in listed:
            errors.append(f"unexpected file: {rel}")
    if errors:
        raise ManifestError(errors)
    return m


def load_ready(d: Path) -> dict:
    """Gate for importers: returns the manifest only if the whole batch validates."""
    return validate(d)


def compare(a: Path, b: Path) -> Dict[str, Tuple[int, bool, bool]]:
    """Per table: (rows, ordered keys identical, chunk checksums identical)."""
    ma, mb = validate(a), validate(b)
    if sorted(ma["tables"]) != sorted(mb["tables"]):
        raise ManifestError(["table sets differ"])
    out = {}
    for t in sorted(ma["tables"]):
        same_keys = list(ordered_keys(Path(a), t, ma)) == list(ordered_keys(Path(b), t, mb))
        same_sums = [c["sha256"] for c in ma["tables"][t]["chunks"]] == [c["sha256"] for c in mb["tables"][t]["chunks"]]
        out[t] = (ma["tables"][t]["row_count"], same_keys, same_sums)
    return out


def _main(argv: List[str]) -> int:
    try:
        if argv[:1] == ["validate"] and len(argv) == 2:
            m = validate(Path(argv[1]).expanduser())
            rows = sum(t["row_count"] for t in m["tables"].values())
            chunks = sum(len(t["chunks"]) for t in m["tables"].values())
            print(f"OK {argv[1]}: {len(m['tables'])} tables, {chunks} chunks, {rows} rows")
            return 0
        if argv[:1] == ["compare"] and len(argv) == 3:
            res = compare(Path(argv[1]).expanduser(), Path(argv[2]).expanduser())
            for t, (n, k, s) in res.items():
                print(f"{t:24} {n:8d} rows  keys_identical={k}  checksums_identical={s}")
            return 0 if all(k for _, k, _ in res.values()) else 1
    except ManifestError as e:
        print(e, file=sys.stderr)
        return 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
