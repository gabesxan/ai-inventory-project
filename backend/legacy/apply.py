"""DB-02 · apply a validated, staged extract idempotently to PostgreSQL (psycopg 3).

What one call does, in ONE transaction (all of it, or none of it):

1. ``manifest.load_ready`` gate, then the DB-06 catalog (categories, suppliers, products) reconciled by
   origin key.
2. History events (``history.read_history``, the same reader the preview uses) into
   ``legacy_history_events``. The stable ``(warehouse_key, record_id)`` makes a repeat a no-op.
3. The DB-12 day-level series into ``legacy_coverage_series`` and ``legacy_coverage_ranges``.
4. Attributable rejections and the batch row (counts, reasons, coverage totals).

Identity and failure
* ``batch_id`` derives from the source system, the warehouse and the extract fingerprint, so the same
  files always give the same batch. A batch that is already ``imported`` is returned untouched.
* A refusal or an error rolls the data transaction back, so a failed batch never publishes a partial
  snapshot. The failure is then recorded in its own transaction as a ``failed`` batch with a reason
  code; a later successful run of the same files replaces that row.
* An extract whose coverage ends before the stored coverage is refused (``stale_extract``): an older
  snapshot must not overwrite newer evidence.

Not done on purpose
* No opening stock, no stock movements and no change to ``products.current_stock`` (DB-10 decision).
  Availability stays ``unknown``; nothing is inferred as zero or as a stockout.
* The DB-08 ticket corrections are not applied (the ledger events already hold the net sales).
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from legacy.catalog_links import CatalogPlan, import_plan
from legacy.history import HistoryRow, Rejection, StagedInputs, read_history
from legacy.identity import SourceInstance
from legacy.manifest import ManifestError, load_ready
from legacy.preview import fingerprint

csv.field_size_limit(10_000_000)

HISTORY_COLUMNS = ("batch_id", "record_id", "warehouse_key", "product_id", "event_date", "event_type", "event_class",
                   "is_demand", "quantity", "signed_quantity", "unit", "unit_cost", "stock_availability", "source_date")
SERIES_COLUMNS = ("warehouse_key", "product_id", "batch_id", "period_start", "period_end", "source", "availability_basis",
                  "days", "sale_days", "true_zero_days", "zero_unknown_availability_days", "known_stockout_days",
                  "unknown_quantity_days", "calendar_gap_days")
RANGE_COLUMNS = ("warehouse_key", "product_id", "start_date", "end_date", "day_status", "batch_id")
DAY_STATUSES = ("sale", "true_zero", "zero_unknown_availability", "known_stockout", "unknown_quantity", "calendar_gap")
# DB-12 status -> API-01 coverage bucket (kept identical to the generated column in migration 0002)
COVERAGE_BUCKET = {"sale": "available_days", "true_zero": "available_days", "known_stockout": "stockout_days",
                   "zero_unknown_availability": "unknown_days", "unknown_quantity": "unknown_days",
                   "calendar_gap": "uncovered_days"}


class ApplyRefused(Exception):
    """A known, row-safe reason to refuse the batch (never a source value)."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass
class ApplyResult:
    batch_id: Optional[str]
    status: str                      # imported | already_imported | failed
    accepted_rows: int = 0
    rejected_rows: int = 0
    duplicate_rows: int = 0
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    coverage: Optional[Dict[str, int]] = None
    period: Optional[Tuple[str, str]] = None
    failure_reason: Optional[str] = None
    series: int = 0
    ranges: int = 0
    stock_movements_created: int = 0


def batch_identity(inst: SourceInstance, warehouse_key: str, fp: str) -> str:
    return "fb-" + hashlib.sha256(f"{inst.system}|{warehouse_key}|{fp}".encode()).hexdigest()[:24]


def _runs(path: Path) -> Iterator[Tuple[str, str, str, str]]:
    """Yield (product_key, status, start_day, end_day) for consecutive days of one product with one status."""
    cur: Optional[List] = None
    with gzip.open(path, "rt", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        for pk, day, status, *_ in reader:
            if cur and cur[0] == pk and cur[1] == status and date.fromisoformat(day) == date.fromisoformat(cur[3]) + timedelta(days=1):
                cur[3] = day
                continue
            if cur:
                yield tuple(cur)  # type: ignore[misc]
            cur = [pk, status, day, day]
    if cur:
        yield tuple(cur)  # type: ignore[misc]


def _load_coverage(cur, staged: StagedInputs, warehouse_key: str, batch_id: str, products: Dict[str, int],
                   rejections: List[Rejection]) -> Tuple[Dict[str, int], int, int, Optional[str], Optional[str]]:
    """Replace the warehouse's coverage with the DB-12 evidence. Returns (bucket totals, series, ranges, start, end)."""
    index_rows = []
    with staged.series_index.open(newline="", encoding="utf-8") as f:  # type: ignore[union-attr]
        reader = csv.DictReader(f)
        for r in reader:
            if r["warehouse_key"] != warehouse_key:
                raise ApplyRefused("coverage_warehouse_mismatch")
            index_rows.append((reader.line_num, r))
    new_end = max((r["period_end"] for _, r in index_rows), default=None)
    cur.execute("SELECT max(period_end) FROM legacy_coverage_series WHERE warehouse_key = %s", (warehouse_key,))
    stored_end = cur.fetchone()[0]
    if stored_end is not None and new_end is not None and date.fromisoformat(new_end) < stored_end:
        raise ApplyRefused("stale_extract")

    cur.execute("DELETE FROM legacy_coverage_ranges WHERE warehouse_key = %s", (warehouse_key,))
    cur.execute("DELETE FROM legacy_coverage_series WHERE warehouse_key = %s", (warehouse_key,))
    totals = {"available_days": 0, "stockout_days": 0, "unknown_days": 0, "uncovered_days": 0}
    expected_days: Dict[str, int] = {}
    start: Optional[str] = None
    with cur.copy(f"COPY legacy_coverage_series ({', '.join(SERIES_COLUMNS)}) FROM STDIN") as cp:
        for line, r in index_rows:
            pid = products.get(r["product_key"])
            if pid is None:
                rejections.append(Rejection("coverage", line, "product_not_in_catalog", r["product_key"]))
                continue
            counts = [int(r[k]) for k in ("sale", "true_zero", "zero_unknown_availability", "known_stockout",
                                          "unknown_quantity", "calendar_gap")]
            cp.write_row((warehouse_key, pid, batch_id, r["period_start"], r["period_end"], r["source"],
                          r["availability_basis"], int(r["days"]), *counts))
            for status, n in zip(DAY_STATUSES, counts):
                totals[COVERAGE_BUCKET[status]] += n
            expected_days[r["product_key"]] = int(r["days"])
            start = r["period_start"] if start is None or r["period_start"] < start else start

    seen_days: Dict[str, int] = {}
    n_ranges = 0
    with cur.copy(f"COPY legacy_coverage_ranges ({', '.join(RANGE_COLUMNS)}) FROM STDIN") as cp:
        for pk, status, first, last in _runs(staged.series):  # type: ignore[arg-type]
            if pk not in expected_days:
                continue
            if status not in DAY_STATUSES:
                raise ApplyRefused("unknown_day_status")
            cp.write_row((warehouse_key, products[pk], first, last, status, batch_id))
            seen_days[pk] = seen_days.get(pk, 0) + (date.fromisoformat(last) - date.fromisoformat(first)).days + 1
            n_ranges += 1
    if seen_days != expected_days:
        raise ApplyRefused("coverage_day_mismatch")
    return totals, len(expected_days), n_ranges, start, new_end


def _record_failure(conn, batch_id: str, inst: SourceInstance, warehouse_key: str, fp: str, reason: str) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "INSERT INTO legacy_import_batches (batch_id, source_system, warehouse_key, source_fingerprint, status, failure_reason) "
            "VALUES (%s, %s, %s, %s, 'failed', %s) "
            "ON CONFLICT (batch_id) DO UPDATE SET status = 'failed', failure_reason = EXCLUDED.failure_reason "
            "WHERE legacy_import_batches.status <> 'imported'", (batch_id, inst.system, warehouse_key, fp, reason))


def apply_extract(conn, extract_dir: Path, staged: StagedInputs, inst: SourceInstance, warehouse_key: str,
                  plan: CatalogPlan, source_date: Optional[str] = None) -> ApplyResult:
    """Apply the extract. ``conn`` must be idle (no open transaction)."""
    if conn.info.transaction_status != 0:
        raise ValueError("apply needs an idle connection (no open transaction)")
    if staged.series_index is None or staged.series is None:
        raise ValueError("the DB-12 day-level series is required to publish coverage")
    try:
        fp = fingerprint(extract_dir, staged)
    except OSError:
        return ApplyResult(None, "failed", failure_reason="manifest_invalid")   # no stable identity to record
    batch_id = batch_identity(inst, warehouse_key, fp)
    try:
        load_ready(extract_dir)
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SELECT status, accepted_rows, rejected_rows, duplicate_rows, rejection_reasons, coverage "
                            "FROM legacy_import_batches WHERE batch_id = %s FOR UPDATE", (batch_id,))
                row = cur.fetchone()
                if row and row[0] == "imported":
                    return ApplyResult(batch_id, "already_imported", row[1], row[2], row[3], row[4], row[5])
                cur.execute(
                    "INSERT INTO legacy_import_batches (batch_id, source_system, warehouse_key, source_fingerprint, status, source_date) "
                    "VALUES (%s, %s, %s, %s, 'failed', %s) ON CONFLICT (batch_id) DO UPDATE SET source_date = EXCLUDED.source_date",
                    (batch_id, inst.system, warehouse_key, fp, source_date))
            import_plan(conn, plan)
            with conn.cursor() as cur:
                cur.execute("SELECT origin_key, target_id FROM legacy_origin WHERE entity = 'product'")
                products = dict(cur.fetchall())
                result = _load_history(cur, staged, inst, warehouse_key, batch_id, source_date, products)
                rejections: List[Rejection] = result.pop("rejections")
                totals, n_series, n_ranges, c_start, c_end = _load_coverage(cur, staged, warehouse_key, batch_id, products, rejections)
                reasons: Dict[str, int] = {}
                for rj in rejections:
                    reasons[rj.reason] = reasons.get(rj.reason, 0) + 1
                with cur.copy("COPY legacy_import_rejections (batch_id, dataset, line_number, reason, record_key) FROM STDIN") as cp:
                    for rj in rejections:
                        cp.write_row((batch_id, rj.dataset, rj.line_number, rj.reason, rj.record_key))
                first = min((d for d in (result["first"], c_start) if d), default=None)
                last = max((d for d in (result["last"], c_end) if d), default=None)
                cur.execute(
                    "UPDATE legacy_import_batches SET status = 'imported', failure_reason = NULL, imported_at = now(), "
                    "accepted_rows = %s, rejected_rows = %s, duplicate_rows = %s, rejection_reasons = %s::jsonb, "
                    "coverage = %s::jsonb, period_start = %s, period_end = %s WHERE batch_id = %s",
                    (result["accepted"], len(rejections), result["duplicate"], json.dumps(reasons), json.dumps(totals),
                     first, last, batch_id))
        return ApplyResult(batch_id, "imported", result["accepted"], len(rejections), result["duplicate"], reasons,
                           totals, (first, last) if first else None, series=n_series, ranges=n_ranges)
    except ApplyRefused as e:
        _record_failure(conn, batch_id, inst, warehouse_key, fp, e.reason)
        return ApplyResult(batch_id, "failed", failure_reason=e.reason)
    except ManifestError:
        _record_failure(conn, batch_id, inst, warehouse_key, fp, "manifest_invalid")
        return ApplyResult(batch_id, "failed", failure_reason="manifest_invalid")
    except Exception:
        _record_failure(conn, batch_id, inst, warehouse_key, fp, "internal_error")
        raise


def _load_history(cur, staged: StagedInputs, inst: SourceInstance, warehouse_key: str, batch_id: str,
                  source_date: Optional[str], products: Dict[str, int]) -> dict:
    cur.execute(f"CREATE TEMP TABLE _legacy_history_in ON COMMIT DROP AS SELECT {', '.join(HISTORY_COLUMNS)} "
                "FROM legacy_history_events WITH NO DATA")
    rejections: List[Rejection] = []
    valid = 0
    first = last = None
    with cur.copy(f"COPY _legacy_history_in ({', '.join(HISTORY_COLUMNS)}) FROM STDIN") as cp:
        for item in read_history(staged, inst, warehouse_key):
            if isinstance(item, Rejection):
                rejections.append(item)
                continue
            row: HistoryRow = item
            pid = products.get(row.product_key)
            if pid is None:
                rejections.append(Rejection("events" if row.event_class != "receipt" else "receipts", None,
                                            "product_not_in_catalog", row.record_id))
                continue
            valid += 1
            first = row.event_date if first is None or row.event_date < first else first
            last = row.event_date if last is None or row.event_date > last else last
            cp.write_row((batch_id, row.record_id, warehouse_key, pid, row.event_date, row.event_type, row.event_class,
                          row.is_demand, row.quantity, row.signed_quantity, row.unit, row.unit_cost,
                          row.stock_availability, source_date))
    cols = ", ".join(HISTORY_COLUMNS)
    cur.execute(f"INSERT INTO legacy_history_events ({cols}) SELECT {cols} FROM _legacy_history_in "
                "ON CONFLICT (warehouse_key, record_id) DO NOTHING")
    accepted = cur.rowcount
    return {"accepted": accepted, "duplicate": valid - accepted, "rejections": rejections, "first": first, "last": last}


def _main(argv: List[str]) -> int:
    import argparse
    import sys

    from legacy.catalog_links import build_plan
    from legacy.extract import Extract
    from legacy.identity import location_key

    ap = argparse.ArgumentParser(description="Apply a staged Firebird extract to a DEDICATED PostgreSQL database (DB-02).")
    ap.add_argument("extract_dir", type=Path)
    ap.add_argument("out_dir", type=Path, help="staged outputs of DB-05/07/09/12 (the fb15 out directory)")
    ap.add_argument("--branch", type=int, default=1)
    ap.add_argument("--source-date", default=None, help="verified snapshot date (YYYY-MM-DD); omitted = unknown")
    ap.add_argument("--pg-socket", required=True)
    ap.add_argument("--pg-port", required=True)
    ap.add_argument("--pg-db", required=True)
    a = ap.parse_args(argv)
    import psycopg

    inst = SourceInstance(branch=a.branch)
    plan = build_plan(Extract(a.extract_dir))
    with psycopg.connect(host=a.pg_socket, port=a.pg_port, user="legacy", dbname=a.pg_db) as conn:
        res = apply_extract(conn, a.extract_dir, StagedInputs.from_out_dir(a.out_dir), inst,
                            location_key(inst, a.branch), plan, a.source_date)
    json.dump(res.__dict__, sys.stdout, indent=2, default=str)
    print()
    return 0 if res.status in ("imported", "already_imported") else 1


if __name__ == "__main__":
    raise SystemExit(_main(__import__("sys").argv[1:]))
