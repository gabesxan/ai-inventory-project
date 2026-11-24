"""DB-15 · reconcile an imported warehouse against the aggregate totals of the source extract.

The "source" side is read straight from the validated extract (``ENTRADAS_SAIDAS`` ledger, ``PRODUTOS``,
``FORNECEDORES``, ``GRUPOS``; DB-04 proved the extract equals the Firebird snapshot) and from the
DB-05..DB-12 summaries. The "actual" side is the dedicated PostgreSQL database. Read-only.

Every check ends as one of:
* ``ok``          expected equals actual. Known rejections are part of the identity being checked (the
                  ``note`` names them), so a difference can never be waved through as "explained";
* ``open``        any difference: the real-data acceptance stays open until it is explained and fixed;
* ``unavailable`` the source has no such evidence (no physical stock count), reported as such, never as zero.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from legacy.extract import Extract, dec, val
from legacy.history import StagedInputs, load_products

OUTBOUND_OPS = {"V", "A", "D", "P", "_"}   # DB-07: every other ledger operation is an entry (receipt)
ZERO = Decimal(0)


def _q(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.001"))


def _check(checks: List[dict], cid: str, scope: str, expected, actual, note: str = "") -> None:
    exp = _q(expected) if isinstance(expected, (Decimal, float)) else expected
    act = _q(actual) if isinstance(actual, (Decimal, float)) else actual
    status, diff = "ok", None
    if exp != act:
        diff, status = exp - act, "open"
    checks.append({"id": cid, "scope": scope, "expected": str(exp), "actual": str(act),
                   "diff": None if diff is None else str(diff), "status": status, "note": note})


def reconcile(conn, warehouse_key: str, extract_dir: Path, staged: StagedInputs, summaries: Optional[Dict[str, Path]] = None) -> dict:
    ex = Extract(extract_dir)
    products = load_products(staged.products)                       # source id -> DB-05 row (sku, unit, issues)
    sku_of = {pid: r["sku"] for pid, r in products.items()}
    unit_of = {r["sku"]: r["unit"] for r in products.values()}
    checks: List[dict] = []

    # ---- source side: the ledger, straight from the extract
    ledger_rows = ledger_v = ledger_c_rows = 0
    v_by_sku: Dict[str, Decimal] = defaultdict(Decimal)
    c_by_sku: Dict[str, Decimal] = defaultdict(Decimal)
    for r in ex.rows("ENTRADAS_SAIDAS"):
        ledger_rows += 1
        op, sku, q = val(r["S_OPERACAO"]), sku_of.get(int(r["ID_PRODUTO"])), dec(r["F_QUANTIDADE"]) or ZERO
        if op == "V":
            ledger_v += 1
            v_by_sku[sku] += q
        elif op not in OUTBOUND_OPS:
            ledger_c_rows += 1
            c_by_sku[sku] += q
    rejected_v: Dict[str, Decimal] = defaultdict(Decimal)            # V rows DB-07 refused (quarantined/missing product)
    with staged.events.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["event_type"] == "reject" and r["ledger_op"] == "V":
                rejected_v[sku_of.get(int(r["product_id"]))] += Decimal(r["qty"])

    cur = conn.cursor()
    one = lambda sql, *a: (cur.execute(sql, a), cur.fetchone()[0])[1]   # noqa: E731
    rows = lambda sql, *a: (cur.execute(sql, a), cur.fetchall())[1]     # noqa: E731

    # ---- 1. every ledger row is either staged or an attributable rejection
    staged_rows = one("SELECT count(*) FROM legacy_history_events WHERE warehouse_key = %s", warehouse_key)
    # rejections of the LATEST imported batch: it is the extract that was just compared with the ledger
    rejected = one("SELECT count(*) FROM legacy_import_rejections WHERE dataset IN ('events', 'receipts') AND batch_id = ("
                   "SELECT batch_id FROM legacy_import_batches WHERE warehouse_key = %s AND status = 'imported' "
                   "ORDER BY imported_at DESC, batch_id LIMIT 1)", warehouse_key)
    _check(checks, "ledger_rows", "warehouse", ledger_rows, staged_rows + rejected,
           "ENTRADAS_SAIDAS rows = staged history rows + attributable rejections")

    # ---- 2. sales and corrections per SKU: ledger V = staged sales + corrections + refused V rows
    db_v = {s: q for s, q in rows(
        "SELECT p.sku, sum(e.signed_quantity) FROM legacy_history_events e JOIN products p ON p.id = e.product_id "
        "WHERE e.warehouse_key = %s AND e.event_type IN ('pos_sale', 'sale_correction') GROUP BY p.sku", warehouse_key)}
    bad_v = [s for s in set(v_by_sku) | set(db_v) | set(rejected_v)
             if v_by_sku.get(s, ZERO) != db_v.get(s, ZERO) + rejected_v.get(s, ZERO)]
    _check(checks, "ledger_V_per_sku", "SKU", 0, len(bad_v),
           "ledger V (net daily sales) per SKU = staged pos_sale + sale_correction + V rows refused by DB-07"
           + (f"; first mismatches: {sorted(map(str, bad_v))[:5]}" if bad_v else ""))
    _check(checks, "ledger_V_total", "warehouse", sum(v_by_sku.values(), ZERO),
           sum(db_v.values(), ZERO) + sum(rejected_v.values(), ZERO), "same identity, in total")
    by_unit: Dict[str, List[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for s, q in v_by_sku.items():
        by_unit[unit_of.get(s, "?")][0] += q
    for s, q in db_v.items():
        by_unit[unit_of.get(s, "?")][1] += q
    for s, q in rejected_v.items():
        by_unit[unit_of.get(s, "?")][1] += q
    for u, (e, a) in sorted(by_unit.items()):
        _check(checks, f"ledger_V_unit_{u or 'none'}", f"unit {u or 'none'}", e, a)

    # ---- 3. receipts per SKU: ledger entries = staged receipts (refused receipts carry no quantity)
    db_c = {s: q for s, q in rows(
        "SELECT p.sku, sum(e.quantity) FROM legacy_history_events e JOIN products p ON p.id = e.product_id "
        "WHERE e.warehouse_key = %s AND e.event_class = 'receipt' GROUP BY p.sku", warehouse_key)}
    bad_c = [s for s in set(c_by_sku) | set(db_c) if c_by_sku.get(s, ZERO) != db_c.get(s, ZERO)]
    _check(checks, "ledger_receipts_per_sku", "SKU", 0, len(bad_c),
           "ledger entries per SKU = staged receipts" + (f"; first mismatches: {sorted(map(str, bad_c))[:5]}" if bad_c else ""))
    _check(checks, "ledger_receipts_total", "warehouse", sum(c_by_sku.values(), ZERO), sum(db_c.values(), ZERO))

    # ---- 4. per event type against the DB-07 summary (rows and quantity), refused rows excluded
    if summaries and summaries.get("db07"):
        s7 = json.loads(Path(summaries["db07"]).read_text())
        for etype, t in sorted(s7["events_by_type"].items()):
            if etype == "reject":
                continue
            n, q = rows("SELECT count(*), coalesce(sum(signed_quantity), 0) FROM legacy_history_events "
                        "WHERE warehouse_key = %s AND event_type = %s", warehouse_key, etype)[0]
            _check(checks, f"db07_{etype}_rows", etype, t["rows"], n)
            _check(checks, f"db07_{etype}_qty", etype, Decimal(t["qty"]), q)
        _check(checks, "db07_demand_qty", "warehouse", Decimal(s7["verified_demand_qty"]), one(
            "SELECT coalesce(sum(quantity), 0) FROM legacy_history_events WHERE warehouse_key = %s AND is_demand", warehouse_key))

    # ---- 5. coverage: series, runs and the DB-12 summary
    totals = rows("SELECT coalesce(sum(days),0), coalesce(sum(sale_days),0), coalesce(sum(true_zero_days),0), "
                  "coalesce(sum(zero_unknown_availability_days),0), coalesce(sum(known_stockout_days),0), "
                  "coalesce(sum(unknown_quantity_days),0), coalesce(sum(calendar_gap_days),0), count(*) "
                  "FROM legacy_coverage_series WHERE warehouse_key = %s", warehouse_key)[0]
    run_days = one("SELECT coalesce(sum(end_date - start_date + 1), 0) FROM legacy_coverage_ranges WHERE warehouse_key = %s", warehouse_key)
    _check(checks, "coverage_ranges_expand_to_series_days", "warehouse", int(totals[0]), int(run_days))
    for status, db_n in zip(("sale", "true_zero", "zero_unknown_availability", "known_stockout", "unknown_quantity", "calendar_gap"), totals[1:7]):
        n = one("SELECT coalesce(sum(end_date - start_date + 1), 0) FROM legacy_coverage_ranges "
                "WHERE warehouse_key = %s AND day_status = %s", warehouse_key, status)
        _check(checks, f"coverage_{status}_days", status, int(db_n), int(n), "series totals = expanded runs")
    if summaries and summaries.get("db12"):
        s12 = json.loads(Path(summaries["db12"]).read_text())
        _check(checks, "db12_product_days", "warehouse", s12["product_days"], int(totals[0]))
        _check(checks, "db12_series", "warehouse", s12["series"], int(totals[7]))
        for status, n in s12["status_counts"].items():
            _check(checks, f"db12_{status}", status, n, int(rows(
                "SELECT coalesce(sum(end_date - start_date + 1), 0) FROM legacy_coverage_ranges "
                "WHERE warehouse_key = %s AND day_status = %s", warehouse_key, status)[0][0]))
    _check(checks, "stockout_or_uncovered_inferred", "warehouse", 0, one(
        "SELECT count(*) FROM legacy_history_events WHERE warehouse_key = %s AND stock_availability IN ('stockout', 'uncovered')",
        warehouse_key), "availability is never inferred as stockout or uncovered")
    _check(checks, "availability_only_on_sales", "warehouse", 0, one(
        "SELECT count(*) FROM legacy_history_events WHERE warehouse_key = %s AND stock_availability = 'available' AND NOT is_demand",
        warehouse_key))

    # ---- 6. catalog and stock
    n_products = sum(1 for r in products.values() if not r["issues"])
    _check(checks, "catalog_products", "catalog", n_products, one("SELECT count(*) FROM products"),
           "staged products without issues")
    _check(checks, "catalog_suppliers", "catalog", ex.count("FORNECEDORES"), one("SELECT count(*) FROM suppliers"))
    _check(checks, "catalog_groups", "catalog", ex.count("GRUPOS"), one("SELECT count(*) FROM categories"))
    _check(checks, "no_stock_movements", "stock", 0, one("SELECT count(*) FROM stock_movements"))
    _check(checks, "no_stock_change", "stock", ZERO, one("SELECT coalesce(sum(current_stock), 0) FROM products"))
    _check(checks, "no_opening_entries", "stock", 0, one("SELECT count(*) FROM legacy_opening_entries"))
    checks.append({"id": "dated_balance", "scope": "stock", "expected": None, "actual": None, "diff": None,
                   "status": "unavailable",
                   "note": "no physical stock count in the source (DB-10); the book balance ESTOQUE_ATUAL is not imported; availability stays unknown"})
    cur.close()
    conn.rollback()
    counts: Dict[str, int] = defaultdict(int)
    for c in checks:
        counts[c["status"]] += 1
    return {"warehouse": warehouse_key, "checks": checks, "summary": dict(counts), "open": counts["open"]}


def snapshot_totals(conn) -> Dict[str, str]:
    """Every total that a repeat or a recovered import must leave unchanged (read-only)."""
    cur = conn.cursor()
    out: Dict[str, str] = {}
    for name, sql in (
        ("products", "SELECT count(*) FROM products"), ("categories", "SELECT count(*) FROM categories"),
        ("suppliers", "SELECT count(*) FROM suppliers"), ("stock_movements", "SELECT count(*) FROM stock_movements"),
        ("sum_current_stock", "SELECT coalesce(sum(current_stock), 0) FROM products"),
        ("history_events", "SELECT count(*) FROM legacy_history_events"),
        ("coverage_series", "SELECT count(*) FROM legacy_coverage_series"),
        ("coverage_ranges", "SELECT count(*) FROM legacy_coverage_ranges"),
        ("coverage_days", "SELECT coalesce(sum(end_date - start_date + 1), 0) FROM legacy_coverage_ranges"),
        ("rejections", "SELECT count(*) FROM legacy_import_rejections"),
        ("batches", "SELECT count(*) FROM legacy_import_batches"),
        ("opening_entries", "SELECT count(*) FROM legacy_opening_entries"),
    ):
        cur.execute(sql)
        out[name] = str(cur.fetchone()[0])
    cur.execute("SELECT event_class, sum(quantity) FROM legacy_history_events GROUP BY 1 ORDER BY 1")
    out.update({f"quantity_{k}": str(v) for k, v in cur.fetchall()})
    cur.close()
    conn.rollback()
    return out
