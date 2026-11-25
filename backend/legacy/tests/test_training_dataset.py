"""DB-12 follow-up · temporal dataset from the real series, on FIXTURE data (no database)."""
import csv
import gzip
import json
from datetime import date, timedelta

import pytest

from legacy.training_dataset import VERIFIED_BASIS, build, split_boundaries

WH = "estoquefacil-fb15/1/local/1"
INDEX = ["product_key", "sku", "unit", "warehouse_key", "period_start", "period_end", "source", "availability_basis",
         "days", "sale", "true_zero", "zero_unknown_availability", "known_stockout", "unknown_quantity", "calendar_gap"]


def days(n):
    return [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(n)]


def write(tmp, rows, basis="sales_evidence_only", skus=("k1", "k2")):
    s = tmp / "series.csv.gz"
    with gzip.open(s, "wt", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["product_key", "day", "status", "demand", "receipts", "available", "uncensored"])
        w.writerows(rows)
    i = tmp / "series_index.csv"
    with i.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(INDEX)
        for k in skus:
            w.writerow([k, "s" + k, "UN", WH, "2025-01-01", "2025-01-20", "ledger", basis, 20, 0, 0, 0, 0, 0, 0])
    return s, i


def series(status_of):
    return [[k, d, *status_of(k, n)] for k in ("k1", "k2") for n, d in enumerate(days(20))]


def sale_or_unknown(k, n):
    if n % 2 == 0:
        return ("sale", "3.000", "0", "1", "1")
    return ("zero_unknown_availability", "0", "0", "", "0")


def rows(out):
    with gzip.open(out / "dataset.csv.gz", "rt", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_unknown_availability_is_excluded_not_turned_into_zero(tmp_path):
    s, i = write(tmp_path, series(sale_or_unknown))
    m = build(s, i, tmp_path / "out", WH)
    data = rows(tmp_path / "out")
    assert m["series_days"] == 40 and m["rows_kept"] == 20 == len(data)
    assert m["excluded_days_by_status"] == {"zero_unknown_availability": 20}
    assert {r["day_status"] for r in data} == {"sale"} and all(float(r["demand"]) > 0 for r in data)   # no invented zeros
    assert all(r["provenance"] == "firebird_real" and r["availability_basis"] == "sales_evidence_only" for r in data)


def test_splits_are_chronological_disjoint_and_complete(tmp_path):
    s, i = write(tmp_path, series(lambda k, n: ("sale", "2.000", "0", "1", "1")))
    m = build(s, i, tmp_path / "out", WH)
    b = m["splits"]
    assert m["chronological_check"] and m["rows_kept"] == 40
    assert b["train"]["last_day"] < b["validation"]["first_day"] <= b["validation"]["last_day"] < b["test"]["first_day"]
    assert sum(v["rows"] for v in b.values()) == 40
    by_split = {}
    for r in rows(tmp_path / "out"):
        by_split.setdefault(r["split"], []).append(r["day"])
    assert max(by_split["train"]) < min(by_split["validation"]) and max(by_split["validation"]) < min(by_split["test"])
    assert (b["train"]["rows"], b["validation"]["rows"], b["test"]["rows"]) == (28, 6, 6)            # 14/3/3 calendar days x 2 SKUs


def test_sales_only_basis_is_never_declared_eligible_for_calibration(tmp_path):
    s, i = write(tmp_path, series(sale_or_unknown))
    m = build(s, i, tmp_path / "out", WH)
    assert m["calibration_eligible"] is False and "conditioned on a sale" in m["calibration_eligibility_reason"]
    assert json.loads((tmp_path / "out" / "dataset-manifest.json").read_text())["calibration_eligible"] is False


def test_only_a_verified_basis_makes_the_dataset_eligible(tmp_path):
    s, i = write(tmp_path, series(lambda k, n: ("true_zero" if n % 3 == 0 else "sale", "0" if n % 3 == 0 else "2.000", "0", "1", "1")),
                 basis=VERIFIED_BASIS)
    m = build(s, i, tmp_path / "out", WH)
    assert m["calibration_eligible"] is True
    assert {r["day_status"] for r in rows(tmp_path / "out")} == {"sale", "true_zero"}


def test_a_calendar_gap_and_an_unknown_quantity_are_excluded(tmp_path):
    s, i = write(tmp_path, series(lambda k, n: ("calendar_gap", "0", "0", "", "0") if n < 5 else
                                  (("unknown_quantity", "", "0", "", "0") if n < 10 else ("sale", "1.000", "0", "1", "1"))))
    m = build(s, i, tmp_path / "out", WH)
    assert m["excluded_days_by_status"] == {"calendar_gap": 10, "unknown_quantity": 10} and m["rows_kept"] == 20


def test_split_boundaries_validate_their_input():
    assert split_boundaries(days(10), (0.7, 0.2, 0.1))["test"][1] == days(10)[-1]
    with pytest.raises(ValueError):
        split_boundaries(days(10), (0.5, 0.5, 0.5))
    with pytest.raises(ValueError):
        split_boundaries(days(2), (0.7, 0.15, 0.15))


def test_a_series_index_of_another_warehouse_is_refused(tmp_path):
    s, i = write(tmp_path, series(sale_or_unknown))
    with pytest.raises(ValueError):
        build(s, i, tmp_path / "out", "another/warehouse")
