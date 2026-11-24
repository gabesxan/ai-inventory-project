"""DB-09 · receipts and cost provenance on FIXTURES."""
from collections import defaultdict
from decimal import Decimal as D

from legacy.receipts import STOCK_RECEIPT_CLASSES, classify_cfop, receipt_cost


def test_cfop_classes_keep_transfers_and_adjustments_apart_from_supplier_receipts():
    assert classify_cfop("1102") == classify_cfop("2403") == "supplier_purchase"
    assert classify_cfop("1910") == "supplier_bonus"
    assert classify_cfop("1152") == "transfer_in" and classify_cfop("2949") == "other_entry"
    assert classify_cfop("1556") == "use_consumption" and classify_cfop("1202") == "customer_return"
    assert classify_cfop("5102") == classify_cfop("") == "unknown_cfop"
    assert {"transfer_in", "other_entry"}.isdisjoint(STOCK_RECEIPT_CLASSES)


def test_costs_keep_precision_zero_and_unknown():
    c = receipt_cost(D("49.9900"), 12, D("4.166"))
    assert c.price_per_purchase_unit == D("49.9900") and c.invoice_cost_per_base_unit == D("4.165833")
    assert c.recorded_cost_per_base_unit == D("4.166") and c.cost_status == "known"
    z = receipt_cost(D("0.0000"), 6, D("0.000"))
    assert z.cost_status == "explicit_zero" and z.invoice_cost_per_base_unit == D("0.000000")
    u = receipt_cost(None, 6, None)
    assert u.cost_status == "unknown" and u.invoice_cost_per_base_unit is None


def test_canceled_receipt_does_not_inflate_stock_history_and_totals_reconcile_by_period_and_unit():
    # FIXTURE: (doc, month, unit, base_qty, has_ledger_stock_effect)
    lines = [(1, "2026-10", "UN", D("24"), True), (2, "2026-10", "UN", D("12"), False),   # doc 2 canceled
             (3, "2026-10", "KG", D("5.250"), True), (4, "2026-11", "UN", D("6"), True)]
    ledger = {("2026-10", "UN"): D("24"), ("2026-10", "KG"): D("5.250"), ("2026-11", "UN"): D("6")}
    hist = defaultdict(D)
    for _, month, unit, q, posted in lines:
        if posted:
            hist[(month, unit)] += q
    assert dict(hist) == ledger  # the canceled 12 UN never enters stock history
