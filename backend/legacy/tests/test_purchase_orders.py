"""DB-11 · purchase-order pipeline on FIXTURES (the real source has no orders)."""
from decimal import Decimal as D

from legacy.purchase_orders import UNAVAILABLE, OrderLine, Receipt, apply_receipts, lead_times, pipeline


def lines():
    return [OrderLine("po1/1", 10, 7, D("24"), "2026-11-01", "2026-11-10"),
            OrderLine("po1/2", 11, 7, D("12"), None, "2026-12-15"),               # order date missing
            OrderLine("po2/1", 12, 8, D("6"), "2026-11-02", "2026-11-05", canceled=True)]


def test_partial_receipt_reduces_outstanding_correctly():
    by_id = apply_receipts(lines(), [Receipt("nf9/1", "po1/1", "2026-11-06", D("10")),
                                     Receipt("nf9/1", "po1/1", "2026-11-06", D("10")),   # duplicate delivery
                                     Receipt("nf10/1", None, "2026-11-07", D("5"))])     # no documented key
    assert by_id["po1/1"].outstanding == D("14")
    assert by_id["po2/1"].outstanding == D("0")                                           # canceled remainder
    assert pipeline(by_id.values(), "2026-11-08") == {"due_0_7": D("14"), "due_31_plus": D("12")}


def test_missing_order_date_stays_null_and_unknown_pipeline_stays_unavailable():
    by_id = apply_receipts(lines(), [Receipt("a", "po1/1", "2026-11-06", D("24")), Receipt("b", "po1/2", "2026-11-20", D("12"))])
    assert lead_times(by_id.values()) == [5, None]
    assert pipeline(None, "2026-11-23") == UNAVAILABLE          # no orders in the source: not zero
