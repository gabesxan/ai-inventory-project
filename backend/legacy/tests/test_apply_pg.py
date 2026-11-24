"""DB-02 · idempotent apply of a staged extract against an ISOLATED, DISPOSABLE PostgreSQL (FIXTURE data)."""
import csv
import gzip
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from datetime import date, timedelta
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from legacy import apply as apply_mod  # noqa: E402
from legacy.apply import apply_extract  # noqa: E402
from legacy.catalog_links import CatalogPlan  # noqa: E402
from legacy.history import StagedInputs  # noqa: E402
from legacy.identity import SourceInstance  # noqa: E402
from legacy.tests.test_preview import EVENT_COLS, PRODUCT_COLS, RECEIPT_COLS, _csv, _event, _product  # noqa: E402
from legacy.tests.test_staging_pg import alembic, connect, newdb, row_counts  # noqa: E402,F401

SOCK, PORT = os.environ.get("LEGACY_PG_SOCKET"), os.environ.get("LEGACY_PG_PORT")
pytestmark = pytest.mark.skipif(not (SOCK and PORT), reason="disposable PostgreSQL not configured")
INST = SourceInstance(branch=1)
WH = "estoquefacil-fb15/1/local/1"
P1, P2 = "estoquefacil-fb15/1/produto/1", "estoquefacil-fb15/1/produto/2"
INDEX_COLS = ["product_key", "sku", "unit", "warehouse_key", "period_start", "period_end", "source", "availability_basis",
              "days", "sale", "true_zero", "zero_unknown_availability", "known_stockout", "unknown_quantity", "calendar_gap"]


def plan():
    p = CatalogPlan()
    p.categories = {"i/grupo/1": "GERAL"}
    p.products = {k: {"sku": s, "name": "P" + s, "unit": u, "barcode": None, "is_active": True, "category": "i/grupo/1",
                      "preferred_supplier": None} for k, s, u in ((P1, "000001", "UN"), (P2, "000002", "KG"))}
    return p


def build(tmp, name, last_day="2025-07-22", extra_events=()):
    """A staged extract whose DB-12 series runs 2025-07-20..last_day. P1 sells from 07-21, P2 never."""
    d, out = tmp / name, tmp / (name + "-out")
    d.mkdir()
    (d / "manifest.json").write_text('{"format_version": 1, "tables": {}}')
    days = [(date(2025, 7, 20) + timedelta(days=i)).isoformat() for i in range((date.fromisoformat(last_day) - date(2025, 7, 20)).days + 1)]
    _csv(out / "db05/products.csv", PRODUCT_COLS, [_product(1, "000001"), _product(2, "000002", "KG"), _product(3, "000003", "", "unknown_unit")])
    _csv(out / "db07/events.csv", EVENT_COLS, [
        _event("m/1", 1, "2025-07-21", "2.000", "pos_sale", 1),
        _event("m/2", 1, "2025-07-22" if "2025-07-22" in days else "2025-07-21", "3.000", "pos_sale", 1) if "2025-07-22" in days
        else _event("m/2b", 1, "2025-07-20", "1.000", "loss"),
        _event("m/3", 2, "2025-07-21", "-1.500", "sale_correction"),
        _event("m/4", 3, "2025-07-21", "1.000", "pos_sale", 1),                 # product without unit: rejected
        _event("m/5", 99, "2025-07-21", "1.000", "pos_sale", 1),                # unknown product: rejected
        *extra_events])
    _csv(out / "db09/stock_receipts.csv", RECEIPT_COLS, [[1, "2025-07-20", "UN", "12.000", "documented", "supplier_purchase", "m/10"]])
    status1 = {d_: ("sale" if d_ >= "2025-07-21" else "zero_unknown_availability") for d_ in days}
    rows, idx = [], []
    for pk, sku, unit, st in ((P1, "1", "UN", status1), (P2, "2", "KG", {d_: "zero_unknown_availability" for d_ in days})):
        rows += [[pk, d_, st[d_], "1.000" if st[d_] == "sale" else "0", "0", "1" if st[d_] == "sale" else "", "1" if st[d_] == "sale" else "0"] for d_ in days]
        n = {k: sum(1 for v in st.values() if v == k) for k in ("sale", "zero_unknown_availability")}
        idx.append([pk, sku, unit, WH, days[0], days[-1], "ledger fixture", "sales_evidence_only", len(days), n["sale"], 0,
                    n["zero_unknown_availability"], 0, 0, 0])
    _csv(out / "db12/series_index.csv", INDEX_COLS, idx)
    with gzip.open(out / "db12/series.csv.gz", "wt", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["product_key", "day", "status", "demand", "receipts", "available", "uncensored"])
        w.writerows(rows)
    return d, StagedInputs.from_out_dir(out)


def snapshot(conn):
    return row_counts(conn)


def apply(conn, d, staged, **kw):
    conn.rollback()                                   # the test's own reads must not leave a transaction open
    return apply_extract(conn, d, staged, INST, WH, plan(), **kw)


@pytest.fixture
def db(newdb):
    name, url = newdb()
    alembic(url, "upgrade", "head")
    with connect(name) as conn:
        yield conn


def test_import_publishes_history_coverage_and_never_stock(db, tmp_path):
    d, staged = build(tmp_path, "a")
    r = apply(db, d, staged)
    assert (r.status, r.accepted_rows, r.rejected_rows, r.duplicate_rows) == ("imported", 4, 2, 0)
    assert r.rejection_reasons == {"product_unknown_unit": 1, "unknown_product": 1}
    assert r.coverage == {"available_days": 2, "stockout_days": 0, "unknown_days": 4, "uncovered_days": 0}
    assert (r.series, r.ranges, r.period) == (2, 3, ("2025-07-20", "2025-07-22"))
    q = lambda sql: db.execute(sql).fetchall()
    assert q("SELECT stock_availability, count(*) FROM legacy_history_events GROUP BY 1 ORDER BY 1") == [("available", 2), ("unknown", 2)]
    assert q("SELECT coverage, uncensored, start_date, end_date FROM legacy_coverage_ranges ORDER BY product_id, start_date") == [
        ("unknown", False, date(2025, 7, 20), date(2025, 7, 20)), ("available", True, date(2025, 7, 21), date(2025, 7, 22)),
        ("unknown", False, date(2025, 7, 20), date(2025, 7, 22))]
    assert q("SELECT dataset, reason FROM legacy_import_rejections ORDER BY reason") == [("events", "product_unknown_unit"), ("events", "unknown_product")]
    assert q("SELECT status, accepted_rows, rejected_rows, period_start, period_end, source_date FROM legacy_import_batches") == [
        ("imported", 4, 2, date(2025, 7, 20), date(2025, 7, 22), None)]
    # no opening stock, no stock movement, no stock change: the demo starts with unknown availability
    assert q("SELECT count(*) FROM stock_movements") == [(0,)] and q("SELECT coalesce(sum(current_stock), 0) FROM products") == [(0,)]
    assert q("SELECT count(*) FROM legacy_opening_entries") == [(0,)] and q("SELECT count(*) FROM legacy_opening_snapshots") == [(0,)]


def test_importing_the_same_files_twice_preserves_every_total(db, tmp_path):
    d, staged = build(tmp_path, "a")
    first = apply(db, d, staged)
    before = snapshot(db)
    again = apply(db, d, staged)
    assert again.status == "already_imported" and again.batch_id == first.batch_id
    assert (again.accepted_rows, again.rejected_rows) == (4, 2)
    assert snapshot(db) == before


def test_failed_batch_publishes_nothing_and_a_retry_recovers_the_same_batch(db, tmp_path, monkeypatch):
    d, staged = build(tmp_path, "a")
    before = snapshot(db)
    real = apply_mod._load_coverage

    def boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(apply_mod, "_load_coverage", boom)
    with pytest.raises(RuntimeError):
        apply(db, d, staged)
    after = snapshot(db)
    assert {t: n for t, n in after.items() if t != "legacy_import_batches"} == {t: n for t, n in before.items() if t != "legacy_import_batches"}
    assert db.execute("SELECT status, failure_reason, accepted_rows FROM legacy_import_batches").fetchall() == [("failed", "internal_error", 0)]
    monkeypatch.setattr(apply_mod, "_load_coverage", real)
    ok = apply(db, d, staged)
    assert ok.status == "imported" and ok.accepted_rows == 4
    assert db.execute("SELECT status, failure_reason FROM legacy_import_batches").fetchall() == [("imported", None)]


def test_coverage_that_does_not_add_up_refuses_the_whole_batch(db, tmp_path):
    d, staged = build(tmp_path, "a")
    with gzip.open(staged.series, "rt", encoding="utf-8") as f:
        lines = f.read().splitlines()
    with gzip.open(staged.series, "wt", encoding="utf-8") as f:
        f.write("\n".join(lines[:-1]) + "\n")                              # drop the last day of P2
    r = apply(db, d, staged)
    assert (r.status, r.failure_reason) == ("failed", "coverage_day_mismatch")
    counts = snapshot(db)
    assert counts["legacy_history_events"] == counts["products"] == counts["legacy_coverage_ranges"] == 0
    assert db.execute("SELECT status, failure_reason FROM legacy_import_batches").fetchall() == [("failed", "coverage_day_mismatch")]


def test_unreadable_extract_is_refused_without_touching_the_database(db, tmp_path):
    d, staged = build(tmp_path, "a")
    (d / "manifest.json").unlink()
    before = snapshot(db)
    r = apply(db, d, staged)
    assert (r.status, r.failure_reason, r.batch_id) == ("failed", "manifest_invalid", None)
    assert snapshot(db) == before


def test_newer_overlapping_extract_adds_only_new_rows_and_replaces_coverage(db, tmp_path):
    a_dir, a = build(tmp_path, "a", last_day="2025-07-21")
    assert apply(db, a_dir, a).status == "imported"
    b_dir, b = build(tmp_path, "b", last_day="2025-07-22")
    r = apply(db, b_dir, b)
    assert r.status == "imported" and r.duplicate_rows == 3 and r.accepted_rows == 1       # m/1, m/3, receipt repeat; m/2 is new
    assert db.execute("SELECT count(*) FROM legacy_history_events").fetchone()[0] == 5      # A's 4 rows + B's one new row: no double counting
    assert db.execute("SELECT count(*), max(period_end) FROM legacy_coverage_series").fetchone() == (2, date(2025, 7, 22))
    assert db.execute("SELECT count(*) FROM legacy_import_batches WHERE status = 'imported'").fetchone()[0] == 2


def test_older_extract_cannot_overwrite_newer_coverage(db, tmp_path):
    b_dir, b = build(tmp_path, "b", last_day="2025-07-22")
    assert apply(db, b_dir, b).status == "imported"
    before = db.execute("SELECT count(*) FROM legacy_coverage_ranges").fetchone()[0]
    a_dir, a = build(tmp_path, "a", last_day="2025-07-21")
    r = apply(db, a_dir, a)
    assert (r.status, r.failure_reason) == ("failed", "stale_extract")
    assert db.execute("SELECT count(*), max(period_end) FROM legacy_coverage_series").fetchone() == (2, date(2025, 7, 22))
    assert db.execute("SELECT count(*) FROM legacy_coverage_ranges").fetchone()[0] == before


def test_concurrent_repeat_keeps_the_first_publication(db, tmp_path, monkeypatch):
    d, staged = build(tmp_path, "concurrent")
    entered, release = Event(), Event()
    load_history = apply_mod._load_history

    def pause_first(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(timeout=10)
        return load_history(*args, **kwargs)

    monkeypatch.setattr(apply_mod, "_load_history", pause_first)
    with connect(db.info.dbname) as initial, connect(db.info.dbname) as repeat:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(apply, initial, d, staged)
            assert entered.wait(timeout=10)
            second = pool.submit(apply, repeat, d, staged)
            deadline = monotonic() + 8
            try:
                while monotonic() < deadline:
                    wait_state = db.execute(
                        "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s",
                        (repeat.info.backend_pid,),
                    ).fetchone()
                    db.rollback()
                    if wait_state == ("Lock",):
                        break
                    sleep(0.01)
                else:
                    pytest.fail("The second importer never reached the lock")
            finally:
                release.set()
            published, repeated = first.result(timeout=10), second.result(timeout=10)
    assert (published.status, repeated.status) == ("imported", "already_imported")
    assert published.batch_id == repeated.batch_id
    assert db.execute("SELECT accepted_rows, rejected_rows FROM legacy_import_batches").fetchall() == [(4, 2)]
    assert db.execute("SELECT count(*) FROM legacy_history_events").fetchone() == (4,)
