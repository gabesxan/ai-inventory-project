"""DB-10 · opening snapshot import against an ISOLATED, DISPOSABLE PostgreSQL (FIXTURE data).

Runs only when LEGACY_PG_SOCKET (unix-socket dir) and LEGACY_PG_PORT point to a throwaway
cluster; each run creates and drops its own database after applying the v1 Alembic schema.
"""
import os
import subprocess
import sys
import uuid
from decimal import Decimal as D
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from legacy.opening import Balance, Snapshot, import_snapshot  # noqa: E402

SOCK, PORT = os.environ.get("LEGACY_PG_SOCKET"), os.environ.get("LEGACY_PG_PORT")
pytestmark = pytest.mark.skipif(not (SOCK and PORT), reason="disposable PostgreSQL not configured")
BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def db():
    name = "legacy_db10_" + uuid.uuid4().hex[:8]
    admin = psycopg.connect(host=SOCK, port=PORT, user="legacy", dbname="postgres", autocommit=True)
    admin.execute(f'CREATE DATABASE "{name}"')
    url = f"postgresql+psycopg://legacy@/{name}?host={SOCK}&port={PORT}"
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True,
                   env={**os.environ, "DATABASE_URL": url}, capture_output=True)
    conn = psycopg.connect(host=SOCK, port=PORT, user="legacy", dbname=name)
    with conn.cursor() as c:
        c.execute("INSERT INTO users (name, email, password_hash, role) VALUES ('Importador legado', 'legacy@example.test', 'x', 'ADMIN') RETURNING id")
        uid = c.fetchone()[0]
        c.execute("INSERT INTO categories (name) VALUES ('Legado') RETURNING id")
        cat = c.fetchone()[0]
        for sku in ("000001", "000002", "000003"):
            c.execute("INSERT INTO products (name, sku, category_id, unit) VALUES (%s, %s, %s, 'UN')", ("P" + sku, sku, cat))
    conn.commit()
    yield conn, uid
    conn.close()
    admin.execute(f'DROP DATABASE "{name}"')
    admin.close()


def snap(qty_1="10.000", sid="snapA", date="2025-06-30"):
    return Snapshot(sid, date, "estoquefacil-fb15/1/local/1", "fixture CAD_BALANCO 7", [
        Balance("k/produto/1", "000001", D(qty_1), "UN"),
        Balance("k/produto/2", "000002", D("0.000"), "UN"),     # counted zero: recorded, no movement
        Balance("k/produto/9", "999999", D("4.000"), "UN"),     # SKU not in the catalog
    ])


def state(conn):
    with conn.cursor() as c:
        c.execute("SELECT sku, current_stock FROM products ORDER BY sku")
        stock = dict(c.fetchall())
        c.execute("SELECT count(*) FROM stock_movements WHERE reason_code = 'SALDO_INICIAL'")
        moves = c.fetchone()[0]
        c.execute("SELECT count(*) FROM legacy_opening_entries")
        entries = c.fetchone()[0]
    return stock, moves, entries


def test_reimport_cannot_reset_stock_or_duplicate_openings(db):
    conn, uid = db
    r1 = import_snapshot(conn, snap(), uid)
    assert (r1["created"], r1["zero_recorded"], r1["missing_product"]) == (1, 1, 1)
    first = state(conn)
    assert first == ({"000001": D("10.000"), "000002": D("0.000"), "000003": D("0.000")}, 1, 2)

    r2 = import_snapshot(conn, snap(), uid)                       # same snapshot again
    assert r2["created"] == 0 and r2["already_imported"] == 2
    assert state(conn) == first

    r3 = import_snapshot(conn, snap(qty_1="99.000", sid="snapB", date="2026-01-31"), uid)  # other snapshot
    assert r3["created"] == 0 and ("000001", "opening_exists_from_other_snapshot") in r3["refused"]
    assert state(conn) == first                                   # stock was not reset to 99

    with conn.cursor() as c:                                       # product with history is refused too
        c.execute("UPDATE products SET current_stock = 5 WHERE sku = '000003'")
    conn.commit()
    r4 = import_snapshot(conn, Snapshot("snapC", "2025-06-30", "w", "fixture", [Balance("k/produto/3", "000003", D("8"), "UN")]), uid)
    assert r4["refused"] == [("000003", "product_already_has_stock_history")]


def test_old_snapshot_is_labeled_with_its_actual_date(db):
    conn, uid = db
    import_snapshot(conn, snap(date="2019-03-31"), uid)
    with conn.cursor() as c:
        c.execute("SELECT source_date::text, label FROM legacy_opening_snapshots")
        d, label = c.fetchone()
        c.execute("SELECT notes FROM stock_movements WHERE reason_code = 'SALDO_INICIAL'")
        note = c.fetchone()[0]
        c.execute("SELECT DISTINCT source_date::text FROM legacy_opening_entries")
        entry_dates = [r[0] for r in c.fetchall()]
    assert d == "2019-03-31" and entry_dates == ["2019-03-31"]
    assert "2019-03-31" in label and "2019-03-31" in note  # actual date, not the import date
