"""DB-12 follow-up · temporal train/validation/test dataset from the real daily series, with explicit provenance.

Input is the DB-12 day-level series (``series.csv.gz``) and its index. Rules:

* Only ``uncensored`` days enter: ``sale`` and ``true_zero``. A day with unknown availability
  (``zero_unknown_availability``, ``unknown_quantity``) or a calendar gap is EXCLUDED and counted. It is never
  turned into zero stock or zero demand.
* Splits are chronological by calendar date, never random: every SKU's days follow the same boundaries, so
  nothing from a later period reaches an earlier split.
* Every row says where it came from: ``provenance = firebird_real`` and the series' availability basis.
* This builds data, it does not decide eligibility. ``calibration_eligible`` is true only when every selected
  series has the verified full-day availability basis the calibration gate requires (``verified_stock_history``).
  With ``sales_evidence_only`` the rows are conditioned on a sale having happened (demand > 0), so they are NOT
  a complete demand series and must not train or calibrate a replenishment policy.

Stdlib only.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

UNCENSORED = {"sale", "true_zero"}
VERIFIED_BASIS = "verified_stock_history"          # what app.ai.calibration requires
PROVENANCE = "firebird_real"
COLUMNS = ["product_key", "sku", "unit", "warehouse_key", "day", "split", "demand", "day_status", "availability_basis",
           "provenance"]


def split_boundaries(days: Sequence[str], fractions: Tuple[float, float, float]) -> Dict[str, Tuple[str, str]]:
    """Chronological (first, last) calendar day of each split. The fractions apply to the calendar, not to rows."""
    if abs(sum(fractions) - 1) > 1e-9 or min(fractions) <= 0:
        raise ValueError("fractions must be positive and add up to 1")
    ordered = sorted(set(days))
    n = len(ordered)
    a, b = int(n * fractions[0]), int(n * (fractions[0] + fractions[1]))
    if not (0 < a < b < n):
        raise ValueError("not enough calendar days for three splits")
    return {"train": (ordered[0], ordered[a - 1]), "validation": (ordered[a], ordered[b - 1]), "test": (ordered[b], ordered[-1])}


def _split_of(day: str, bounds: Dict[str, Tuple[str, str]]) -> str:
    for name, (first, last) in bounds.items():
        if first <= day <= last:
            return name
    raise ValueError("day outside the calendar: " + day)


def build(series: Path, series_index: Path, out_dir: Path, warehouse_key: str,
          fractions: Tuple[float, float, float] = (0.70, 0.15, 0.15)) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    meta: Dict[str, Dict[str, str]] = {}
    with series_index.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["warehouse_key"] != warehouse_key:
                raise ValueError("series index belongs to another warehouse")
            meta[r["product_key"]] = r
    calendar = set()
    with gzip.open(series, "rt", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        for _pk, day, *_ in reader:
            calendar.add(day)
    bounds = split_boundaries(sorted(calendar), fractions)

    counts: Counter = Counter()
    excluded: Counter = Counter()
    by_split: Dict[str, Counter] = {s: Counter() for s in bounds}
    skus: Dict[str, set] = {s: set() for s in bounds}
    bases: Counter = Counter()
    rows_path = out_dir / "dataset.csv.gz"
    with gzip.open(series, "rt", newline="", encoding="utf-8") as src, \
            gzip.open(rows_path, "wt", newline="", encoding="utf-8", compresslevel=6) as dst:
        reader, writer = csv.reader(src), csv.writer(dst, lineterminator="\n")
        next(reader)
        writer.writerow(COLUMNS)
        for pk, day, status, demand, _rec, _av, unc in reader:
            counts["series_days"] += 1
            m = meta[pk]
            if status not in UNCENSORED or unc != "1":
                excluded[status] += 1
                continue
            split = _split_of(day, bounds)
            writer.writerow([pk, m["sku"], m["unit"], warehouse_key, day, split, demand, status,
                             m["availability_basis"], PROVENANCE])
            by_split[split]["rows"] += 1
            by_split[split][status] += 1
            skus[split].add(pk)
            bases[m["availability_basis"]] += 1
    digest = hashlib.sha256(rows_path.read_bytes()).hexdigest()
    kept = sum(c["rows"] for c in by_split.values())
    eligible = bool(kept) and set(bases) == {VERIFIED_BASIS}
    manifest = {
        "provenance": PROVENANCE,
        "warehouse_key": warehouse_key,
        "period": [min(calendar), max(calendar)],
        "calendar_days": len(calendar),
        "splits": {s: {"first_day": bounds[s][0], "last_day": bounds[s][1], "rows": by_split[s]["rows"],
                       "skus": len(skus[s]), "by_status": {k: v for k, v in by_split[s].items() if k != "rows"}}
                   for s in bounds},
        "series_days": counts["series_days"],
        "rows_kept": kept,
        "excluded_days_by_status": dict(excluded),
        "excluded_rule": "days without verified availability are excluded; never imputed as zero stock or zero demand",
        "availability_basis": dict(bases),
        "calibration_eligible": eligible,
        "calibration_eligibility_reason": (
            "every selected series has verified full-day availability" if eligible else
            "availability_basis is not verified_stock_history: rows exist only for days with a sale (demand > 0), "
            "so the demand series is incomplete and conditioned on a sale; not usable to train or calibrate a policy"),
        "chronological_check": bounds["train"][1] < bounds["validation"][0] <= bounds["validation"][1] < bounds["test"][0],
        "files": {"dataset.csv.gz": {"sha256": digest, "rows": kept}},
        "columns": COLUMNS,
    }
    (out_dir / "dataset-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _main(argv: List[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Temporal dataset from the real DB-12 series (no imputation).")
    ap.add_argument("out_dir_db12", type=Path, help="fb15/out/db12 (series.csv.gz, series_index.csv)")
    ap.add_argument("dest", type=Path)
    ap.add_argument("--warehouse", default="estoquefacil-fb15/1/local/1")
    a = ap.parse_args(argv)
    m = build(a.out_dir_db12 / "series.csv.gz", a.out_dir_db12 / "series_index.csv", a.dest, a.warehouse)
    print(json.dumps({k: m[k] for k in ("period", "splits", "rows_kept", "excluded_days_by_status", "availability_basis",
                                       "calibration_eligible", "chronological_check")}, indent=2))
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
