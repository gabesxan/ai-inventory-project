"""DB-12 · publish daily SKU series for the demonstration warehouse from the real extract.

    PYTHONPATH=. python3 legacy/firebird/db12/db12_series.py <extract_dir> <db07_out> <db09_out> <out_dir>

Inputs: the validated DB-04 extract (coverage, products), DB-07 events.csv (demand and
undeterminable days) and DB-09 stock_receipts.csv (posted receipts). Writes series.csv.gz,
series_index.csv and summary.json to <out_dir> (outside Git).
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from legacy.coverage import build_series
from legacy.extract import Extract, val
from legacy.identity import SourceInstance, location_key, product_key
from legacy.products import normalize_products

UNKNOWN_EVENTS = {"unverified_outbound", "pending_document", "canceled_document", "sale_correction"}
LEDGER_START_FLOOR = "2024-02-28"  # V/C/VV coverage starts here; 4 V rows dated 2001-01-01 are outliers


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main(extract_dir: str, db07: str, db09: str, out_dir: str) -> dict:
    ex = Extract(Path(extract_dir))
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    inst = SourceInstance(branch=ex.scope["branch"])
    wh = location_key(inst, ex.scope["branch"])
    as_of = ex.scope["as_of"]
    prods = {p.source_id: p for p in normalize_products(inst, ex.rows("PRODUTOS"))}

    covered = {r["D_DATA"] for r in ex.rows("ENTRADAS_SAIDAS") if LEDGER_START_FLOOR <= r["D_DATA"] <= as_of}
    period_start, period_end = min(covered), max(covered)

    ev_path = Path(db07).expanduser() / "events.csv"
    rc_path = Path(db09).expanduser() / "stock_receipts.csv"
    demand = defaultdict(lambda: defaultdict(Decimal))
    unknown = defaultdict(set)
    for r in csv.DictReader(ev_path.open(encoding="utf-8")):
        pid, d = int(r["product_id"]), r["day"]
        if r["is_demand"] == "1":
            demand[pid][d] += Decimal(r["qty"])
        elif r["event_type"] in UNKNOWN_EVENTS:
            unknown[pid].add(d)
    receipts = defaultdict(lambda: defaultdict(Decimal))
    for r in csv.DictReader(rc_path.open(encoding="utf-8")):
        if r["day"] <= as_of:
            receipts[int(r["product_id"])][r["day"]] += Decimal(r["qty_base"])

    status_total = Counter()
    n_series = 0
    with gzip.open(out / "series.csv.gz", "wt", newline="", encoding="utf-8") as gz, \
            (out / "series_index.csv").open("w", newline="", encoding="utf-8") as ix:
        w = csv.writer(gz, lineterminator="\n")
        w.writerow(["product_key", "day", "status", "demand", "receipts", "available", "uncensored"])
        wi = csv.writer(ix, lineterminator="\n")
        wi.writerow(["product_key", "sku", "unit", "warehouse_key", "period_start", "period_end", "source",
                     "availability_basis", "days", "sale", "true_zero", "zero_unknown_availability",
                     "known_stockout", "unknown_quantity", "calendar_gap"])
        for pid in sorted(set(demand) | set(receipts)):
            p = prods.get(pid)
            if p is None or p.quarantined:
                continue
            acts = [d for d in list(demand[pid]) + list(receipts[pid]) if period_start <= d <= period_end]
            if not acts:
                continue
            start = min(acts)
            avail = {d: True for d, q in demand[pid].items() if q > 0}  # a sale proves stock that day
            s = build_series(p.key, wh, start, period_end,
                             f"ENTRADAS_SAIDAS ledger {period_start}..{period_end}; snapshot fbk {ex.manifest['source']['snapshot_fbk_sha256'][:12]}",
                             covered, demand[pid], receipts[pid], unknown[pid], avail,
                             "sales_evidence_only (no physical opening stock, DB-10)")
            c = Counter(d.status for d in s.days)
            status_total.update(c)
            n_series += 1
            for d in s.days:
                w.writerow([s.product_key, d.day, d.status, "" if d.demand is None else d.demand, d.receipts,
                            "" if d.available is None else int(d.available), int(d.uncensored)])
            wi.writerow([s.product_key, p.sku, p.unit, wh, s.period_start, s.period_end, s.source, s.availability_basis,
                         len(s.days)] + [c.get(k, 0) for k in ("sale", "true_zero", "zero_unknown_availability",
                                                              "known_stockout", "unknown_quantity", "calendar_gap")])
    calendar = len(build_series("x", wh, period_start, period_end, "", covered, {}, {}).days)
    res = {
        "extract": str(ex.path),
        "inputs_sha256": {"db07_events.csv": sha(ev_path), "db09_stock_receipts.csv": sha(rc_path)},
        "warehouse_key": wh,
        "store_period": [period_start, period_end],
        "store_calendar_days": calendar,
        "store_covered_days": len(covered),
        "store_calendar_gaps": calendar - len(covered),
        "series": n_series,
        "product_days": sum(status_total.values()),
        "status_counts": dict(status_total),
        "uncensored_days": status_total["sale"] + status_total["true_zero"],
        "availability_basis": "sales_evidence_only: no physical opening stock (DB-10); zero-sale days stay zero_unknown_availability",
        "known_stockout_source": "none in the snapshot (no balance history)",
    }
    (out / "summary.json").write_text(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:5]), indent=2))
