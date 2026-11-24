"""DB-15 · second-extract and safe-repeat validation of the REAL slice, on a disposable PostgreSQL.

    PYTHONPATH=backend python backend/legacy/firebird/db15/db15_validate.py \
        <extract-a> <extract-b> <out-a> <work-out> --pg-socket DIR --pg-port N [--keep-db NAME]

1. Re-stage extract B (DB-05/07/09/12 scripts) and compare every staged output with A's.
2. Fresh database: apply A, reconcile it against the ledger, apply B (a re-extraction of the same
   snapshot must be the same batch), reconcile again, and compare every total.
3. Fresh database: inject a failure in the middle of the import, prove nothing was published, then
   import for real and compare with step 2.
Evidence is written to ``<work-out>`` (JSON + Markdown), outside Git. The exit code is 0 only when
nothing is open.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg

from legacy import apply as apply_mod
from legacy.apply import apply_extract
from legacy.catalog_links import build_plan
from legacy.extract import Extract
from legacy.history import StagedInputs
from legacy.identity import SourceInstance, location_key
from legacy.reconcile import reconcile, snapshot_totals

BACKEND = Path(__file__).resolve().parents[3]
STAGED = {"db05": "products.csv", "db07": "events.csv", "db09": "stock_receipts.csv",
          "db09/receipt_lines": "receipt_lines.csv", "db12/series_index": "series_index.csv", "db12/series": "series.csv.gz"}


def digest(p: Path) -> str:
    h = hashlib.sha256()
    with (gzip.open(p, "rb") if p.suffix == ".gz" else p.open("rb")) as f:    # content, not the gzip header
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def restage(extract_b: Path, out_b: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(BACKEND)}
    run = lambda *a: subprocess.run([sys.executable, *map(str, a)], cwd=BACKEND, env=env, check=True, capture_output=True)  # noqa: E731
    fb = BACKEND / "legacy" / "firebird"
    run(fb / "db05" / "db05_products.py", extract_b, out_b / "db05")
    run(fb / "db07" / "db07_sales.py", extract_b, out_b / "db07")
    run(fb / "db09" / "db09_receipts.py", extract_b, out_b / "db09")
    run(fb / "db12" / "db12_series.py", extract_b, out_b / "db07", out_b / "db09", out_b / "db12")


def new_db(admin, sock, port, name: str):
    admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    admin.execute(f'CREATE DATABASE "{name}"')
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True, capture_output=True,
                   env={**os.environ, "DATABASE_URL": f"postgresql+psycopg://legacy@/{name}?host={sock}&port={port}"})
    return psycopg.connect(host=sock, port=port, user="legacy", dbname=name)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("extract_a", type=Path)
    ap.add_argument("extract_b", type=Path)
    ap.add_argument("out_a", type=Path)
    ap.add_argument("work_out", type=Path)
    ap.add_argument("--pg-socket", required=True)
    ap.add_argument("--pg-port", required=True)
    ap.add_argument("--keep-db", default=None, help="keep the first database under this name (else drop it)")
    a = ap.parse_args(argv)
    a.work_out.mkdir(parents=True, exist_ok=True)
    out_b = a.work_out / "staged-b"
    inst = SourceInstance(branch=1)
    wh = location_key(inst, 1)
    ev: dict = {"warehouse": wh, "extract_a": str(a.extract_a), "extract_b": str(a.extract_b)}

    # 1. re-extraction: the staged outputs of B must equal A's
    restage(a.extract_b, out_b)
    sa, sb = StagedInputs.from_out_dir(a.out_a), StagedInputs.from_out_dir(out_b)
    pairs = [(n, getattr(sa, n), getattr(sb, n)) for n in ("products", "events", "receipts", "receipt_lines", "series_index", "series")]
    ev["restaged"] = {n: {"a": digest(pa)[:16], "b": digest(pb)[:16], "equal": digest(pa) == digest(pb)} for n, pa, pb in pairs}

    admin = psycopg.connect(host=a.pg_socket, port=a.pg_port, user="legacy", dbname="postgres", autocommit=True)
    summaries = {"db07": a.out_a / "db07" / "summary.json", "db12": a.out_a / "db12" / "summary.json"}
    plan_a = build_plan(Extract(a.extract_a))
    plan_b = build_plan(Extract(a.extract_b))

    # 2. clean import, reconcile, repeat from the second extract
    name1 = a.keep_db or "db15_" + uuid.uuid4().hex[:8]
    c1 = new_db(admin, a.pg_socket, a.pg_port, name1)
    r1 = apply_extract(c1, a.extract_a, sa, inst, wh, plan_a)
    t1, rec1 = snapshot_totals(c1), reconcile(c1, wh, a.extract_a, sa, summaries)
    r2 = apply_extract(c1, a.extract_b, sb, inst, wh, plan_b)
    t2, rec2 = snapshot_totals(c1), reconcile(c1, wh, a.extract_b, sb, summaries)
    ev["clean_import"] = {"status": r1.status, "batch_id": r1.batch_id, "accepted": r1.accepted_rows, "rejected": r1.rejected_rows,
                          "duplicate": r1.duplicate_rows, "reasons": r1.rejection_reasons, "totals": t1, "reconcile": rec1["summary"]}
    ev["rerun_from_second_extract"] = {"status": r2.status, "same_batch": r2.batch_id == r1.batch_id,
                                       "totals_identical": t1 == t2, "totals": t2, "reconcile": rec2["summary"]}
    ev["reconcile_checks"] = rec2["checks"]
    c1.close()
    if not a.keep_db:
        admin.execute(f'DROP DATABASE "{name1}" WITH (FORCE)')

    # 3. partial failure on the real slice: fail after the history is staged, then recover
    name2 = "db15_" + uuid.uuid4().hex[:8]
    c2 = new_db(admin, a.pg_socket, a.pg_port, name2)
    real = apply_mod._load_coverage

    def fail_after_history(*args, **kw):
        raise RuntimeError("injected failure after the history was staged")
    apply_mod._load_coverage = fail_after_history
    try:
        apply_extract(c2, a.extract_a, sa, inst, wh, plan_a)
        raised = False
    except RuntimeError:
        raised = True
    finally:
        apply_mod._load_coverage = real
    c2.rollback()
    after_fail = snapshot_totals(c2)
    cur = c2.cursor()
    cur.execute("SELECT status, failure_reason FROM legacy_import_batches")
    failed_rows = cur.fetchall()
    c2.rollback()
    published = {k: v for k, v in after_fail.items() if k not in ("batches",) and v not in ("0", "0.000")}
    r3 = apply_extract(c2, a.extract_a, sa, inst, wh, plan_a)
    t3 = snapshot_totals(c2)
    ev["partial_failure"] = {"raised": raised, "published_after_failure": published, "batch_rows_after_failure": failed_rows,
                             "recovered_status": r3.status, "same_batch": r3.batch_id == r1.batch_id,
                             "totals_equal_clean_import": t3 == t1}
    c2.close()
    admin.execute(f'DROP DATABASE "{name2}" WITH (FORCE)')
    admin.close()

    ok = (all(v["equal"] for v in ev["restaged"].values()) and r1.status == "imported" and r2.status == "already_imported"
          and ev["rerun_from_second_extract"]["same_batch"] and t1 == t2 and rec1["open"] == 0 and rec2["open"] == 0
          and raised and not published and failed_rows == [("failed", "internal_error")]
          and r3.status == "imported" and t3 == t1)
    ev["acceptable"] = bool(ok)
    (a.work_out / "db15-validation.json").write_text(json.dumps(ev, indent=2, default=str))
    print(json.dumps({k: ev[k] for k in ("restaged", "rerun_from_second_extract", "partial_failure", "acceptable")}, indent=2, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
