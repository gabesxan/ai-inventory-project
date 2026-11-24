"""DB-13 · read-only import preview over a validated, staged extract.

``preview`` returns the API-01 ``LegacyImportPreview`` shape (docs/contracts/report-v1) as a plain dict,
so this module stays stdlib-only. It never writes: the optional database connection is switched to
READ ONLY (PostgreSQL itself rejects a write) and rolled back, and the operational tables are not
touched. Confirmation is a separate step (DB-02).

* The extract must pass ``manifest.load_ready``; otherwise the preview is ``invalid`` with one
  ``manifest_invalid`` diagnostic and no rows.
* ``total_rows = valid_rows + rejected_rows + duplicate_rows``. A duplicate is a record key seen
  earlier in the same extract or already staged in ``legacy_history_events`` for the warehouse.
* ``status`` is ``invalid`` as soon as any row is rejected or the manifest fails. Rejected rows are
  attributable (dataset, file line, reason code) and do not stop a later import of the valid ones.
* ``source_date`` is null unless the caller can verify the snapshot date. It is never guessed.
* ``diagnostics`` is capped (counts stay exact); ``reason_counts`` has the full tally.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from legacy.history import HistoryRow, Rejection, StagedInputs, read_history
from legacy.identity import SourceInstance, location_key
from legacy.manifest import ManifestError, load_ready

MAX_DIAGNOSTICS = 200


@dataclass
class PreviewResult:
    preview: Dict[str, Any]
    reason_counts: Dict[str, int] = field(default_factory=dict)
    class_counts: Dict[str, int] = field(default_factory=dict)
    period: Optional[List[str]] = None
    fingerprint: Optional[str] = None


def _sha256(p: Path) -> str:
    """Hash of the CONTENT: a .gz is hashed decompressed, because its header carries a timestamp."""
    h = hashlib.sha256()
    with (gzip.open(p, "rb") if p.suffix == ".gz" else p.open("rb")) as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _manifest_identity(extract_dir: Path) -> str:
    """Hash of the manifest WITHOUT its ``run`` block (extraction time and path).

    Every table hash stays in. Re-extracting the same snapshot therefore keeps its identity, while any
    change to the data, the scope or the source changes it.
    """
    m = json.loads((extract_dir / "manifest.json").read_text(encoding="utf-8"))
    m.pop("run", None)
    return hashlib.sha256(json.dumps(m, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fingerprint(extract_dir: Path, staged: StagedInputs) -> str:
    """Identity of the extract content and staged inputs; the same data always gives the same value."""
    parts = [_manifest_identity(extract_dir)]
    for p in (staged.products, staged.events, staged.receipts, staged.receipt_lines, staged.series_index, staged.series):
        if p is not None:
            parts.append(_sha256(p))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def _already_staged(conn, warehouse_key: str) -> Set[str]:
    """Record ids already staged for the warehouse (empty before the 0002 migration). Read-only."""
    if conn is None:
        return set()
    if conn.info.transaction_status != 0:  # psycopg.pq.TransactionStatus.IDLE
        raise ValueError("preview needs an idle connection (no open transaction)")
    conn.read_only = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('legacy_history_events') IS NOT NULL")
            if not cur.fetchone()[0]:
                return set()
            cur.execute("SELECT record_id FROM legacy_history_events WHERE warehouse_key = %s", (warehouse_key,))
            return {r[0] for r in cur}
    finally:
        conn.rollback()
        conn.read_only = False


def _invalid(warehouse_key: str, source_date: Optional[str], reason: str) -> PreviewResult:
    return PreviewResult(
        preview={"schema_version": 1, "status": "invalid", "source": "firebird", "warehouse": warehouse_key,
                 "source_date": source_date, "total_rows": 0, "valid_rows": 0, "rejected_rows": 0,
                 "duplicate_rows": 0,
                 "diagnostics": [{"dataset": "manifest", "line_number": None, "reason": reason}]},
        reason_counts={reason: 1})


def preview(extract_dir: Path, staged: StagedInputs, inst: SourceInstance, warehouse_key: str,
            source_date: Optional[str] = None, conn=None, max_diagnostics: int = MAX_DIAGNOSTICS) -> PreviewResult:
    try:
        load_ready(extract_dir)
    except ManifestError:
        return _invalid(warehouse_key, source_date, "manifest_invalid")

    seen = _already_staged(conn, warehouse_key)
    valid = rejected = duplicate = 0
    reasons: Dict[str, int] = {}
    classes: Dict[str, int] = {}
    diagnostics: List[Dict[str, Any]] = []
    first: Optional[str] = None
    last: Optional[str] = None

    for item in read_history(staged, inst, warehouse_key):
        if isinstance(item, Rejection):
            rejected += 1
            reasons[item.reason] = reasons.get(item.reason, 0) + 1
            if len(diagnostics) < max_diagnostics:
                diagnostics.append({"dataset": item.dataset, "line_number": item.line_number, "reason": item.reason})
            continue
        row: HistoryRow = item
        if row.record_id in seen:
            duplicate += 1
            continue
        seen.add(row.record_id)
        valid += 1
        classes[row.event_class] = classes.get(row.event_class, 0) + 1
        first = row.event_date if first is None or row.event_date < first else first
        last = row.event_date if last is None or row.event_date > last else last

    return PreviewResult(
        preview={"schema_version": 1, "status": "invalid" if rejected else "ready", "source": "firebird",
                 "warehouse": warehouse_key, "source_date": source_date, "total_rows": valid + rejected + duplicate,
                 "valid_rows": valid, "rejected_rows": rejected, "duplicate_rows": duplicate,
                 "diagnostics": diagnostics},
        reason_counts=dict(sorted(reasons.items())), class_counts=dict(sorted(classes.items())),
        period=[first, last] if first else None, fingerprint=fingerprint(extract_dir, staged))


def _main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Read-only preview of a staged Firebird extract (DB-13).")
    ap.add_argument("extract_dir", type=Path)
    ap.add_argument("out_dir", type=Path, help="staged outputs of DB-05/07/09 (the fb15 out directory)")
    ap.add_argument("--branch", type=int, default=1)
    ap.add_argument("--source-date", default=None, help="verified snapshot date (YYYY-MM-DD); omitted = unknown")
    ap.add_argument("--pg-socket", default=None)
    ap.add_argument("--pg-port", default=None)
    ap.add_argument("--pg-db", default=None)
    a = ap.parse_args(argv)
    inst = SourceInstance(branch=a.branch)
    warehouse = location_key(inst, a.branch)
    conn = None
    if a.pg_db:
        import psycopg
        conn = psycopg.connect(host=a.pg_socket, port=a.pg_port, user="legacy", dbname=a.pg_db)
    try:
        res = preview(a.extract_dir, StagedInputs.from_out_dir(a.out_dir), inst, warehouse, a.source_date, conn)
    finally:
        if conn is not None:
            conn.close()
    json.dump({"preview": res.preview, "reason_counts": res.reason_counts, "class_counts": res.class_counts,
               "period": res.period, "fingerprint": res.fingerprint}, sys.stdout, indent=2)
    print()
    return 0 if res.preview["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
