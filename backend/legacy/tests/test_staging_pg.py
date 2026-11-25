"""DB-13 · 0002 staging migration and read-only preview against an ISOLATED, DISPOSABLE PostgreSQL.

Runs only when LEGACY_PG_SOCKET (unix-socket dir) and LEGACY_PG_PORT point to a throwaway cluster;
each test creates and drops its own database. FIXTURE data only.
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402

from legacy.history import StagedInputs  # noqa: E402
from legacy.identity import SourceInstance  # noqa: E402
from legacy.preview import preview  # noqa: E402
from legacy.tests.test_preview import (  # noqa: E402
    EVENT_COLS, PRODUCT_COLS, RECEIPT_COLS, _csv, _event, _product)

SOCK, PORT = os.environ.get("LEGACY_PG_SOCKET"), os.environ.get("LEGACY_PG_PORT")
pytestmark = pytest.mark.skipif(not (SOCK and PORT), reason="disposable PostgreSQL not configured")
BACKEND = Path(__file__).resolve().parents[2]
INST = SourceInstance(branch=1)
WH = "estoquefacil-fb15/1/local/1"

NEW_TABLES = {"legacy_import_batches", "legacy_history_events", "legacy_coverage_series",
              "legacy_import_rejections", "legacy_coverage_ranges", "legacy_opening_snapshots", "legacy_opening_entries",
              "legacy_origin", "legacy_product_suppliers", "legacy_unresolved_links"}


def alembic(url, *args):
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, check=True,
                   env={**os.environ, "DATABASE_URL": url}, capture_output=True)


@pytest.fixture
def newdb():
    created = []
    admin = psycopg.connect(host=SOCK, port=PORT, user="legacy", dbname="postgres", autocommit=True)

    def make():
        name = "legacy_db13_" + uuid.uuid4().hex[:8]
        admin.execute(f'CREATE DATABASE "{name}"')
        created.append(name)
        return name, f"postgresql+psycopg://legacy@/{name}?host={SOCK}&port={PORT}"

    yield make
    for name in created:
        admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    admin.close()


def connect(name):
    return psycopg.connect(host=SOCK, port=PORT, user="legacy", dbname=name)


def tables(conn):
    with conn.cursor() as c:
        c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        return {r[0] for r in c}


def row_counts(conn):
    """Row count of every table: any operational or staging change shows up here."""
    out = {}
    with conn.cursor() as c:
        for t in sorted(tables(conn)):
            c.execute(f'SELECT count(*) FROM "{t}"')
            out[t] = c.fetchone()[0]
    conn.rollback()                                                              # end the read-only snapshot
    return out


def seed_v1(conn):
    with conn.cursor() as c:
        c.execute("INSERT INTO users (name, email, password_hash, role) VALUES ('Admin', 'a@example.test', 'x', 'ADMIN') RETURNING id")
        uid = c.fetchone()[0]
        c.execute("INSERT INTO categories (name) VALUES ('Geral') RETURNING id")
        cat = c.fetchone()[0]
        c.execute("INSERT INTO products (name, sku, category_id, unit, current_stock) VALUES ('P1', '000001', %s, 'UN', 7) RETURNING id", (cat,))
        pid = c.fetchone()[0]
        c.execute("INSERT INTO stock_movements (product_id, movement_type, reason_code, is_demand, quantity, signed_quantity, "
                  "unit_snapshot, balance_before, balance_after, user_id) VALUES (%s, 'ENTRADA', 'RECEBIMENTO', false, 7, 7, 'UN', 0, 7, %s)", (pid, uid))
    conn.commit()
    return pid


@pytest.fixture
def staged(tmp_path):
    out = tmp_path / "out"
    _csv(out / "db05/products.csv", PRODUCT_COLS, [_product(1, "000001")])
    _csv(out / "db07/events.csv", EVENT_COLS, [
        _event("m/1", 1, "2025-07-21", "2.000", "pos_sale", 1),
        _event("m/2", 1, "2025-07-22", "3.000", "pos_sale", 1),
        _event("m/3", 1, "2025-07-22", "x", "pos_sale", 1)])
    _csv(out / "db09/stock_receipts.csv", RECEIPT_COLS, [])
    d = tmp_path / "run"
    d.mkdir()
    (d / "manifest.json").write_text('{"format_version": 1, "tables": {}}')
    return d, StagedInputs.from_out_dir(out)


def test_single_integrated_alembic_head_merges_reports_and_operational_source():
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert script.get_heads() == ["0004_integrated_operational"]
    assert set(script.get_revision("0004_integrated_operational").down_revision) == {
        "0003_integrated_reports", "0003_operational_source",
    }
    assert set(script.get_revision("0003_integrated_reports").down_revision) == {
        "0002_legacy_staging", "0002_replenishment_runs",
    }
    assert script.get_revision("0002_legacy_staging").down_revision == "0001_initial_schema"


def test_clean_install_creates_staging_tables(newdb):
    name, url = newdb()
    alembic(url, "upgrade", "head")
    with connect(name) as conn:
        assert NEW_TABLES | {"replenishment_runs", "replenishment_snapshots"} <= tables(conn)
        with conn.cursor() as c:
            c.execute("SELECT version_num FROM alembic_version")
            assert c.fetchall() == [("0004_integrated_operational",)]


def test_upgrade_from_v1_keeps_data_and_downgrade_is_clean(newdb):
    name, url = newdb()
    alembic(url, "upgrade", "0001_initial_schema")
    with connect(name) as conn:
        assert not NEW_TABLES & tables(conn)
        seed_v1(conn)
        before = row_counts(conn)
    alembic(url, "upgrade", "head")
    with connect(name) as conn:
        after = row_counts(conn)
        assert {t: n for t, n in after.items() if t in before} == before        # v1 data untouched
        assert all(after[t] == 0 for t in NEW_TABLES)
    alembic(url, "downgrade", "0001_initial_schema")
    with connect(name) as conn:
        assert not NEW_TABLES & tables(conn)
        assert row_counts(conn) == before
    alembic(url, "upgrade", "head")                                              # and back again


@pytest.mark.parametrize("v1_first", [False, True], ids=["fresh_database", "existing_v1_data"])
def test_preview_is_read_only_on_fresh_and_v1_databases(newdb, staged, v1_first):
    name, url = newdb()
    alembic(url, "upgrade", "0001_initial_schema" if v1_first else "head")
    if v1_first:
        with connect(name) as conn:
            seed_v1(conn)
        alembic(url, "upgrade", "head")
    extract, inputs = staged
    with connect(name) as conn:
        before = row_counts(conn)
        res = preview(extract, inputs, INST, WH, conn=conn)
        assert conn.read_only is False and conn.info.transaction_status == 0   # restored and released
        assert row_counts(conn) == before                                      # operational + staging unchanged
    assert (res.preview["valid_rows"], res.preview["rejected_rows"], res.preview["duplicate_rows"]) == (2, 1, 0)
    assert res.preview["diagnostics"] == [{"dataset": "events", "line_number": 4, "reason": "invalid_quantity"}]


class SpyCursor(psycopg.Cursor):
    """Records PostgreSQL's own ``transaction_read_only`` while the preview's queries run."""
    seen = []

    def execute(self, query, params=None, **kw):
        result = super().execute(query, params, **kw)
        SpyCursor.seen.append(psycopg.Cursor(self.connection).execute("SHOW transaction_read_only").fetchone()[0])
        return result


def test_preview_queries_run_in_a_read_only_transaction(newdb, staged):
    name, url = newdb()
    alembic(url, "upgrade", "head")
    extract, inputs = staged
    SpyCursor.seen = []
    with psycopg.connect(host=SOCK, port=PORT, user="legacy", dbname=name, cursor_factory=SpyCursor) as conn:
        preview(extract, inputs, INST, WH, conn=conn)
        assert SpyCursor.seen and set(SpyCursor.seen) == {"on"}
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):             # PostgreSQL enforces it, not just us
            conn.read_only = True
            conn.execute("INSERT INTO categories (name) VALUES ('x')")
        conn.rollback()


def test_preview_counts_records_already_staged_as_duplicates(newdb, staged):
    name, url = newdb()
    alembic(url, "upgrade", "head")
    extract, inputs = staged
    with connect(name) as conn:
        pid = seed_v1(conn)
        with conn.cursor() as c:
            c.execute("INSERT INTO legacy_import_batches (batch_id, source_system, warehouse_key, source_fingerprint, status) "
                      "VALUES ('b1', 'estoquefacil-fb15', %s, 'f1', 'imported')", (WH,))
            c.execute("INSERT INTO legacy_history_events (batch_id, record_id, warehouse_key, product_id, event_date, event_type, "
                      "event_class, is_demand, quantity, signed_quantity, unit) VALUES ('b1', 'm/1', %s, %s, '2025-07-21', "
                      "'pos_sale', 'sale', true, 2, 2, 'UN')", (WH, pid))
        conn.commit()
        res = preview(extract, inputs, INST, WH, conn=conn)
    assert (res.preview["valid_rows"], res.preview["duplicate_rows"], res.preview["rejected_rows"]) == (1, 1, 1)


def test_staging_constraints_keep_unknown_availability_explicit(newdb):
    name, url = newdb()
    alembic(url, "upgrade", "head")
    with connect(name) as conn:
        pid = seed_v1(conn)
        with conn.cursor() as c:
            c.execute("INSERT INTO legacy_import_batches (batch_id, source_system, warehouse_key, source_fingerprint, status) "
                      "VALUES ('b1', 'estoquefacil-fb15', 'w', 'f1', 'imported')")
        conn.commit()

        def insert(rec, avail=None, qty="2", signed="2"):
            cols = "(batch_id, record_id, warehouse_key, product_id, event_date, event_type, event_class, is_demand, quantity, signed_quantity, unit"
            vals = [("b1", rec, "w", pid, "2025-07-21", "pos_sale", "sale", True, qty, signed, "UN")]
            sql = cols + (", stock_availability" if avail else "") + ") VALUES (" + ", ".join(["%s"] * (11 + bool(avail))) + ")"
            with conn.cursor() as c:
                c.execute("INSERT INTO legacy_history_events " + sql, vals[0] + ((avail,) if avail else ()))

        insert("r1")                                                     # availability defaults to unknown
        with conn.cursor() as c:
            c.execute("SELECT stock_availability FROM legacy_history_events WHERE record_id = 'r1'")
            assert c.fetchone()[0] == "unknown"
        conn.commit()
        for bad, kwargs in (("dup", {}), ("r2", {"avail": "maybe"}), ("r3", {"qty": "2", "signed": "5"}),
                            ("r4", {"qty": "-2", "signed": "-2"})):
            with pytest.raises(psycopg.errors.IntegrityError):
                insert("r1" if bad == "dup" else bad, **kwargs)
            conn.rollback()


def test_coverage_ranges_derive_contract_coverage_and_calibration_flag(newdb):
    name, url = newdb()
    alembic(url, "upgrade", "head")
    with connect(name) as conn:
        pid = seed_v1(conn)
        with conn.cursor() as c:
            c.execute("INSERT INTO legacy_import_batches (batch_id, source_system, warehouse_key, source_fingerprint, status) "
                      "VALUES ('b1', 'estoquefacil-fb15', 'w', 'f1', 'imported')")
            for i, st in enumerate(("sale", "true_zero", "zero_unknown_availability", "known_stockout",
                                    "unknown_quantity", "calendar_gap")):
                c.execute("INSERT INTO legacy_coverage_ranges (warehouse_key, product_id, start_date, end_date, day_status, batch_id) "
                          "VALUES ('w', %s, %s::date + %s, %s::date + %s, %s, 'b1')", (pid, "2025-01-01", i, "2025-01-01", i, st))
            c.execute("SELECT day_status, coverage, uncensored FROM legacy_coverage_ranges ORDER BY start_date")
            got = c.fetchall()
        assert got == [("sale", "available", True), ("true_zero", "available", True),
                       ("zero_unknown_availability", "unknown", False), ("known_stockout", "stockout", False),
                       ("unknown_quantity", "unknown", False), ("calendar_gap", "uncovered", False)]
        conn.commit()
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.cursor() as c:
                c.execute("INSERT INTO legacy_coverage_ranges (warehouse_key, product_id, start_date, end_date, day_status, batch_id) "
                          "VALUES ('w', %s, '2026-01-01', '2026-01-02', 'available', 'b1')", (pid,))
