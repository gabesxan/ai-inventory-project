"""DB-13 · import preview and staged history reader on FIXTURE data (synthetic, no database)."""
import csv
import json
from decimal import Decimal as D
from pathlib import Path

import pytest

from legacy.history import HistoryRow, StagedInputs, read_history
from legacy.identity import SourceInstance
from legacy.preview import fingerprint, preview

INST = SourceInstance(branch=1)
WH = "estoquefacil-fb15/1/local/1"
PRODUCT_COLS = ["key", "source_id", "sku", "name", "unit", "source_unit", "weighed", "active", "barcode",
                "units_per_pack", "group_id", "department_id", "issues"]
EVENT_COLS = ["movement_key", "product_id", "day", "ledger_op", "qty", "event_type", "is_demand", "reason", "doc_keys"]
RECEIPT_COLS = ["product_id", "day", "unit", "qty_base", "provenance", "classes", "movement_keys"]
LINE_COLS = ["line_key", "doc_key", "supplier_key", "product_id", "day", "cfop", "class", "qty_recorded",
             "units_per_pack", "qty_base", "unit", "price_per_purchase_unit", "invoice_cost_per_base_unit",
             "recorded_cost_per_base_unit", "cost_status", "status"]


def _csv(path: Path, cols, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        w.writerows(rows)
    return path


def _product(i, sku, unit="UN", issues=""):
    return [f"estoquefacil-fb15/1/produto/{i}", i, sku, f"P{sku}", unit, unit, 0, 1, "", 1, 1, 1, issues]


def _event(key, pid, day, qty, etype, demand=0):
    return [key, pid, day, "V", qty, etype, demand, "", ""]


@pytest.fixture
def extract(tmp_path):
    d = tmp_path / "run"
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"format_version": 1, "tables": {}}))
    return d


@pytest.fixture
def staged(tmp_path):
    out = tmp_path / "out"
    _csv(out / "db05/products.csv", PRODUCT_COLS,
         [_product(1, "000001"), _product(2, "000002", "KG"), _product(3, "000003", "", "unknown_unit")])
    _csv(out / "db07/events.csv", EVENT_COLS, [
        _event("m/1", 1, "2025-07-21", "2.000", "pos_sale", 1),             # line 2: valid sale
        _event("m/2", 2, "2025-07-21", "-1.500", "sale_correction"),        # line 3: valid, negative day
        _event("m/1", 1, "2025-07-21", "2.000", "pos_sale", 1),             # line 4: duplicate key
        _event("m/3", 99, "2025-07-21", "1.000", "pos_sale", 1),            # line 5: unknown product
        _event("m/4", 1, "2025-02-30", "1.000", "pos_sale", 1),             # line 6: invalid date
        _event("m/5", 1, "2025-07-22", "abc", "pos_sale", 1),               # line 7: invalid quantity
        _event("m/6", 1, "2025-07-22", "1.000", "reject"),                  # line 8: does not move stock
        _event("m/7", 3, "2025-07-22", "1.000", "pos_sale", 1),             # line 9: product without unit
        _event("m/8", 1, "2025-07-22", "4.000", "loss"),                    # line 10: valid other outbound
        _event("m/9", 1, "2025-07-22", "4.000", "mystery"),                 # line 11: unknown event type
    ])
    _csv(out / "db09/stock_receipts.csv", RECEIPT_COLS, [
        [1, "2025-07-20", "UN", "12.000", "documented", "supplier_purchase", "m/10"],   # line 2: valid
        [2, "2025-07-20", "KG", "0.000", "documented", "supplier_purchase", "m/11"],    # line 3: invalid quantity
    ])
    _csv(out / "db09/receipt_lines.csv", LINE_COLS, [
        ["l/1", "d/1", "s/1", 1, "2025-07-20", "1102", "supplier_purchase", "1", "1", "4.000", "UN", "2", "2.500000", "2.5", "known", "posted"],
        ["l/2", "d/1", "s/1", 1, "2025-07-20", "1102", "supplier_purchase", "1", "1", "8.000", "UN", "2", "3.000000", "3", "known", "posted"],
        ["l/3", "d/2", "s/1", 1, "2025-07-20", "1102", "supplier_purchase", "1", "1", "", "UN", "2", "9.000000", "9", "known", "missing_product"],
    ])
    return StagedInputs.from_out_dir(out)


def _run(extract, staged, **kw):
    return preview(extract, staged, INST, WH, **kw)


def test_counts_and_attributable_diagnostics(extract, staged):
    r = _run(extract, staged)
    p = r.preview
    assert (p["valid_rows"], p["rejected_rows"], p["duplicate_rows"]) == (4, 7, 1)
    assert p["total_rows"] == p["valid_rows"] + p["rejected_rows"] + p["duplicate_rows"] == 12
    assert p["status"] == "invalid" and p["source"] == "firebird" and p["warehouse"] == WH
    assert {(d["dataset"], d["line_number"], d["reason"]) for d in p["diagnostics"]} == {
        ("events", 5, "unknown_product"), ("events", 6, "invalid_date"), ("events", 7, "invalid_quantity"),
        ("events", 8, "document_does_not_move_stock"), ("events", 9, "product_unknown_unit"),
        ("events", 11, "unknown_event_type"), ("receipts", 3, "invalid_quantity")}
    assert r.reason_counts["invalid_quantity"] == 2
    assert r.class_counts == {"other_outbound": 1, "receipt": 1, "return": 1, "sale": 1}
    assert r.period == ["2025-07-20", "2025-07-22"]


def test_matches_api01_contract_shape(extract, staged):
    reports = pytest.importorskip("app.schemas.reports")
    model = reports.LegacyImportPreview.model_validate(_run(extract, staged).preview)
    assert model.status == "invalid" and model.source_date is None and model.rejected_rows == 7


def test_source_date_is_unknown_unless_supplied(extract, staged):
    assert _run(extract, staged).preview["source_date"] is None
    assert _run(extract, staged, source_date="2026-11-23").preview["source_date"] == "2026-11-23"


def test_reasons_never_carry_source_values(extract, staged):
    text = json.dumps(_run(extract, staged).preview)
    for leak in ("abc", "2025-02-30", "m/3", "m/4", "P000001"):
        assert leak not in text


def test_diagnostics_are_capped_but_counts_stay_exact(extract, staged):
    r = _run(extract, staged, max_diagnostics=2)
    assert len(r.preview["diagnostics"]) == 2 and r.preview["rejected_rows"] == 7


def test_clean_extract_is_ready(extract, tmp_path):
    out = tmp_path / "clean"
    _csv(out / "db05/products.csv", PRODUCT_COLS, [_product(1, "000001")])
    _csv(out / "db07/events.csv", EVENT_COLS, [_event("m/1", 1, "2025-07-21", "2.000", "pos_sale", 1)])
    _csv(out / "db09/stock_receipts.csv", RECEIPT_COLS, [])
    r = _run(extract, StagedInputs.from_out_dir(out))
    assert r.preview["status"] == "ready" and r.preview["diagnostics"] == [] and r.preview["valid_rows"] == 1


def test_unvalidated_extract_is_invalid_without_rows(tmp_path, staged):
    r = _run(tmp_path / "missing", staged)
    assert r.preview["status"] == "invalid" and r.preview["total_rows"] == 0
    assert r.preview["diagnostics"] == [{"dataset": "manifest", "line_number": None, "reason": "manifest_invalid"}]


def test_history_rows_keep_unknown_availability_and_direction(staged):
    rows = {x.record_id: x for x in read_history(staged, INST, WH) if isinstance(x, HistoryRow)}
    sale, corr, loss = rows["m/1"], rows["m/2"], rows["m/8"]
    assert (sale.stock_availability, sale.is_demand, sale.event_class) == ("available", True, "sale")
    assert (corr.quantity, corr.signed_quantity, corr.stock_availability) == (D("1.500"), D("-1.500"), "unknown")
    assert (loss.stock_availability, loss.is_demand) == ("unknown", False)
    rec = rows[f"{INST.tag}/receipt/1/2025-07-20/UN"]
    assert (rec.event_class, rec.stock_availability, rec.quantity) == ("receipt", "unknown", D("12.000"))
    # quantity-weighted invoice cost of the two posted lines: (4*2.5 + 8*3) / 12; the missing_product line is ignored
    assert rec.unit_cost == D("2.833333")
    assert not any(r.stock_availability in ("stockout", "uncovered") for r in rows.values())


def test_fingerprint_is_stable_and_changes_with_content(extract, staged):
    a = fingerprint(extract, staged)
    assert a == fingerprint(extract, staged)
    with staged.events.open("a", encoding="utf-8") as f:
        f.write("m/99,1,2025-07-23,V,1.000,pos_sale,1,,\n")
    assert fingerprint(extract, staged) != a


def test_receipt_without_document_or_quantity_is_not_a_zero_receipt(extract, staged):
    with staged.receipts.open("a", encoding="utf-8") as f:
        f.write("1,2025-07-21,UN,0.000,ledger_without_document,supplier_purchase,m/12\n")
    r = _run(extract, staged)
    assert {"dataset": "receipts", "line_number": 4, "reason": "receipt_quantity_unavailable"} in r.preview["diagnostics"]
    assert r.reason_counts["receipt_quantity_unavailable"] == 1 and r.class_counts["receipt"] == 1
