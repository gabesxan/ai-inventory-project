"""DB-15 · reconciliation of an imported warehouse against the extract's ledger (FIXTURE, disposable PostgreSQL)."""
import os

import pytest

psycopg = pytest.importorskip("psycopg")
from legacy.reconcile import reconcile  # noqa: E402
from legacy.tests.test_apply_pg import WH, apply, build, db  # noqa: E402,F401
from legacy.tests.test_staging_pg import newdb  # noqa: E402,F401
from legacy.tests.test_manifest import _write_extract  # noqa: E402
from legacy.tests.test_preview import EVENT_COLS, _csv, _event  # noqa: E402

SOCK, PORT = os.environ.get("LEGACY_PG_SOCKET"), os.environ.get("LEGACY_PG_PORT")
pytestmark = pytest.mark.skipif(not (SOCK and PORT), reason="disposable PostgreSQL not configured")

LEDGER = (["ID", "ID_PRODUTO", "S_OPERACAO", "F_QUANTIDADE", "D_DATA"], [
    ["1", "1", "V", "2.000", "2025-07-21"], ["2", "1", "V", "3.000", "2025-07-22"],
    ["3", "2", "V", "-1.500", "2025-07-21"], ["4", "3", "V", "1.000", "2025-07-21"],      # product 3: no unit, refused
    ["5", "1", "C", "12.000", "2025-07-20"]])


def imported(db, tmp_path):
    d, staged = build(tmp_path, "a")
    _csv(staged.events, EVENT_COLS, [
        _event("m/1", 1, "2025-07-21", "2.000", "pos_sale", 1), _event("m/2", 1, "2025-07-22", "3.000", "pos_sale", 1),
        _event("m/3", 2, "2025-07-21", "-1.500", "sale_correction"), _event("m/4", 3, "2025-07-21", "1.000", "reject")])
    _write_extract(d, {"ENTRADAS_SAIDAS": LEDGER, "PRODUTOS": (["ID"], [["1"], ["2"], ["3"]]),
                       "FORNECEDORES": (["ID"], []), "GRUPOS": (["ID"], [["1"]])})
    assert apply(db, d, staged).status == "imported"
    db.rollback()
    return d, staged


def by_id(report):
    return {c["id"]: c for c in report["checks"]}


def test_a_clean_import_reconciles_with_the_ledger_and_reports_unavailable_balance(db, tmp_path):
    d, staged = imported(db, tmp_path)
    report = reconcile(db, WH, d, staged)
    assert report["open"] == 0, [c for c in report["checks"] if c["status"] == "open"]
    c = by_id(report)
    assert c["ledger_rows"]["expected"] == "5" and c["ledger_V_total"]["expected"] == "4.500"
    assert c["ledger_receipts_total"]["actual"] == "12.000"
    assert c["no_stock_movements"]["status"] == "ok" and c["no_stock_change"]["status"] == "ok"
    assert c["dated_balance"]["status"] == "unavailable"                         # explicit, never zero


def test_a_changed_quantity_is_reported_open_and_attributed(db, tmp_path):
    d, staged = imported(db, tmp_path)
    db.execute("UPDATE legacy_history_events SET quantity = quantity + 1, signed_quantity = signed_quantity + 1 "
               "WHERE record_id = 'm/1'")
    db.commit()
    report = reconcile(db, WH, d, staged)
    c = by_id(report)
    assert report["open"] >= 2
    assert c["ledger_V_per_sku"]["status"] == "open" and "000001" in c["ledger_V_per_sku"]["note"]
    assert c["ledger_V_total"]["diff"] == "-1.000" and c["ledger_V_unit_UN"]["status"] == "open"


def test_a_missing_row_breaks_the_row_identity(db, tmp_path):
    d, staged = imported(db, tmp_path)
    db.execute("DELETE FROM legacy_history_events WHERE record_id = 'm/2'")
    db.commit()
    c = by_id(reconcile(db, WH, d, staged))
    assert c["ledger_rows"]["status"] == "open" and c["ledger_rows"]["diff"] == "1"


def test_a_second_batch_does_not_double_count_rejections(db, tmp_path):
    d, staged = imported(db, tmp_path)
    db.execute("INSERT INTO legacy_import_batches (batch_id, source_system, warehouse_key, source_fingerprint, status, imported_at) "
               "VALUES ('older', 'estoquefacil-fb15', %s, 'old', 'imported', now() - interval '1 day')", (WH,))
    db.execute("INSERT INTO legacy_import_rejections (batch_id, dataset, line_number, reason) VALUES ('older', 'events', 2, 'invalid_date')")
    db.commit()
    assert by_id(reconcile(db, WH, d, staged))["ledger_rows"]["status"] == "ok"
