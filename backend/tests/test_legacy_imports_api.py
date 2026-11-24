"""DB-14 · evidências de importação do banco legado (admin) sobre PostgreSQL real, com dados FIXTURE."""

import csv
import io
import json
from collections.abc import Generator

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.schemas.reports import ImportQualityRow, VersionedReport
from legacy.apply import apply_extract
from legacy.tests.test_apply_pg import INST, WH, build, plan
from legacy.history import StagedInputs  # noqa: F401
from tests.conftest import TEST_DB_URL, test_engine

URL = "/api/ai/imports/legacy/batches"
LEGACY_TABLES = ("legacy_import_batches, legacy_origin, legacy_unresolved_links, legacy_product_suppliers, "
                 "legacy_opening_snapshots")


@pytest.fixture(autouse=True)
def clean_legacy_tables() -> Generator[None, None, None]:
    with test_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {LEGACY_TABLES} RESTART IDENTITY CASCADE"))
    yield


def insert_batch(batch_id, *, warehouse="w1", status="imported", imported_at="2026-11-23T12:00:00Z", accepted=2,
                 rejected=1, duplicate=0, reasons=None, coverage=None, source_date="2025-07-31",
                 failure_reason=None, fingerprint=None):
    with test_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO legacy_import_batches (batch_id, source_system, warehouse_key, source_fingerprint, status, "
            "source_date, period_start, period_end, imported_at, accepted_rows, rejected_rows, duplicate_rows, "
            "rejection_reasons, coverage, failure_reason) VALUES (:b, 'estoquefacil-fb15', :w, :f, :s, :sd, "
            "'2025-07-21', '2025-07-22', :t, :a, :r, :d, CAST(:rr AS jsonb), CAST(:c AS jsonb), :fr)"),
            {"b": batch_id, "w": warehouse, "f": fingerprint or "fp-" + batch_id, "s": status, "sd": source_date,
             "t": imported_at, "a": accepted, "r": rejected, "d": duplicate,
             "rr": json.dumps(reasons if reasons is not None else {"invalid_unit": 1}),
             "c": None if coverage is None else json.dumps(coverage), "fr": failure_reason})


COVERAGE = {"available_days": 0, "stockout_days": 1, "unknown_days": 1, "uncovered_days": 0}


def test_admin_sees_reasons_and_counts_tied_to_a_batch(client: TestClient, admin_headers):
    insert_batch("b-new", coverage=COVERAGE)
    insert_batch("b-old", imported_at="2026-11-20T09:00:00Z", accepted=5, rejected=2, reasons={"invalid_unit": 1, "unknown_product": 1})
    res = client.get(URL, headers=admin_headers)
    assert res.status_code == 200
    body = VersionedReport[ImportQualityRow].model_validate(res.json())
    assert (body.status, body.status_message, body.total, body.page, body.page_size, body.total_pages) == ("ready", None, 2, 1, 25, 1)
    assert [i.batch_id for i in body.items] == ["b-new", "b-old"]                  # import date descending
    one = client.get(URL, headers=admin_headers, params={"batch_id": "b-old"}).json()["items"][0]
    assert (one["accepted_rows"], one["rejected_rows"], one["rejection_reasons"], one["coverage"]) == (5, 2, {"invalid_unit": 1, "unknown_product": 1}, None)
    assert one["source"] == "firebird" and one["warehouse"] == "w1" and one["status"] == "imported"
    assert one["imported_at"] == "2026-11-20T09:00:00Z"                              # UTC, as in the shared fixtures


def test_operator_and_anonymous_are_denied(client: TestClient, operator_headers):
    insert_batch("b1")
    denied = client.get(URL, headers=operator_headers)
    assert denied.status_code == 403 and denied.json() == {"detail": "Acesso restrito a administradores."}
    assert client.get(URL, params={"export": "csv"}, headers=operator_headers).status_code == 403
    assert client.get(URL).status_code == 401


def test_empty_filter_page_size_and_order(client: TestClient, admin_headers):
    insert_batch("b-a", imported_at="2026-11-23T12:00:00Z")
    insert_batch("b-b", imported_at="2026-11-23T12:00:00Z")                        # same date: batch id ascending
    insert_batch("b-fail", status="failed", imported_at=None, accepted=0, rejected=0, failure_reason="stale_extract")
    ids = lambda **p: [i["batch_id"] for i in client.get(URL, headers=admin_headers, params=p).json()["items"]]  # noqa: E731
    assert ids() == ["b-a", "b-b", "b-fail"]                                        # failed (no import date) last
    assert ids(page_size=2) == ["b-a", "b-b"] and ids(page_size=2, page=2) == ["b-fail"]
    empty = client.get(URL, headers=admin_headers, params={"warehouse": "nowhere"}).json()
    assert (empty["status"], empty["items"], empty["total"], empty["total_pages"]) == ("empty", [], 0, 1)
    assert empty["status_message"] == "Nenhum lote de importação no recorte selecionado."
    assert client.get(URL, headers=admin_headers, params={"page_size": 201}).status_code == 422


def test_csv_has_the_same_rows_order_and_values_as_json(client: TestClient, admin_headers):
    insert_batch("b-a", coverage=COVERAGE, reasons={"unknown_product": 1, "invalid_unit": 2})
    insert_batch("b-fail", status="failed", imported_at=None, accepted=0, rejected=0, reasons={})
    js = client.get(URL, headers=admin_headers, params={"page_size": 1}).json()
    res = client.get(URL, headers=admin_headers, params={"export": "csv", "page_size": 1})   # pagination is ignored
    assert res.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(res.text)))
    assert [r["batch_id"] for r in rows] == ["b-a", "b-fail"] and js["total"] == 2
    first = rows[0]
    item = js["items"][0]
    assert first["rejection_reasons"] == json.dumps(item["rejection_reasons"], sort_keys=True, separators=(",", ":"))
    assert json.loads(first["coverage"]) == item["coverage"]
    assert (first["warehouse"], first["source"], first["source_date"], first["imported_at"]) == ("w1", "firebird", "2025-07-31", item["imported_at"])
    assert (rows[1]["imported_at"], rows[1]["coverage"]) == ("", "")                # null -> empty cell
    filtered = list(csv.DictReader(io.StringIO(client.get(URL, headers=admin_headers, params={"export": "csv", "batch_id": "b-fail"}).text)))
    assert [r["batch_id"] for r in filtered] == ["b-fail"]
    empty = client.get(URL, headers=admin_headers, params={"export": "csv", "warehouse": "none"})
    assert empty.status_code == 200 and empty.text.count("\n") == 1               # header only


def test_response_keeps_internals_and_source_values_out(client: TestClient, admin_headers):
    insert_batch("b1", fingerprint="SECRET-FINGERPRINT", failure_reason="internal_error", coverage=COVERAGE)
    for params in ({}, {"export": "csv"}):
        text_ = client.get(URL, headers=admin_headers, params=params).text
        assert "SECRET-FINGERPRINT" not in text_ and "internal_error" not in text_ and "fingerprint" not in text_.lower()


def test_totals_match_what_the_loader_wrote(client: TestClient, admin_headers, tmp_path):
    d, staged = build(tmp_path, "a")
    dsn = make_url(TEST_DB_URL).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn) as conn:
        result = apply_extract(conn, d, staged, INST, WH, plan())
        assert result.status == "imported"
        again = apply_extract(conn, d, staged, INST, WH, plan())                   # a repeat adds no batch
        assert again.status == "already_imported"
    body = client.get(URL, headers=admin_headers, params={"warehouse": WH}).json()
    item = body["items"][0]
    assert body["total"] == 1 and item["batch_id"] == result.batch_id
    assert (item["accepted_rows"], item["rejected_rows"], item["duplicate_rows"]) == (4, 2, 0)
    assert item["rejection_reasons"] == result.rejection_reasons == {"product_unknown_unit": 1, "unknown_product": 1}
    assert item["coverage"] == result.coverage == {"available_days": 2, "stockout_days": 0, "unknown_days": 4, "uncovered_days": 0}
    with test_engine.connect() as conn:
        n = lambda sql: conn.execute(text(sql)).scalar_one()  # noqa: E731
        assert n("SELECT count(*) FROM legacy_history_events") == item["accepted_rows"]
        assert n("SELECT count(*) FROM legacy_import_rejections") == item["rejected_rows"]
        assert n("SELECT count(*) FROM stock_movements") == 0
