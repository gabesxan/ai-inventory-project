"""DB-07 · mixed outbound FIXTURE: only verified sales count as demand."""
from decimal import Decimal as D

from legacy.outbound import Doc, classify, demand_total, summarize

MIXED = [
    # (movement, product, day, op, qty, docs, internal_doc)
    (1, 10, "2026-11-02", "V", D("12.000"), [], False),                                # POS sale
    (2, 10, "2026-11-02", "A", D("5.000"), [Doc(900, "5102", "1")], False),             # posted invoice sale
    (3, 10, "2026-11-03", "A", D("4.000"), [Doc(901, "5102", "0")], False),             # pending document
    (4, 10, "2026-11-03", "A", D("3.000"), [Doc(902, "5102", "3")], False),             # canceled document
    (5, 10, "2026-11-04", "_", D("2.000"), [Doc(903, "5927", "1")], False),             # loss write-off
    (6, 10, "2026-11-04", "A", D("6.000"), [Doc(904, "5152", "1")], False),             # transfer
    (7, 10, "2026-11-05", "D", D("1.000"), [Doc(905, "5202", "1")], False),             # return to supplier
    (8, 10, "2026-11-05", "A", D("1.000"), [Doc(906, "6949", "1")], False),             # warranty exchange
    (9, 10, "2026-11-06", "P", D("0.500"), [], True),                                   # internal outbound
    (10, 10, "2026-11-06", "A", D("7.000"), [], False),                                 # no document: unverified
    (11, 10, "2026-11-07", "V", D("0.000"), [], False),                                 # zero row
    (12, 10, "2026-11-07", "V", D("-1.000"), [], False),                                # negative total (DB-08)
    (13, 10, "2026-11-08", "A", D("2.000"), [Doc(907, "5102", "1"), Doc(908, "5927", "1")], False),  # ambiguous
]


def test_mixed_fixture_counts_only_verified_sales_as_demand():
    ev = [classify(m, p, d, op, q, docs, internal) for m, p, d, op, q, docs, internal in MIXED]
    by_id = {e.movement_id: e.event_type for e in ev}
    assert by_id == {1: "pos_sale", 2: "invoice_sale", 3: "pending_document", 4: "canceled_document", 5: "loss",
                     6: "transfer", 7: "supplier_return", 8: "warranty_exchange", 9: "internal_outbound",
                     10: "unverified_outbound", 11: "reject", 12: "sale_correction", 13: "unverified_outbound"}
    assert demand_total(ev) == D("17.000")  # 12 POS + 5 posted invoice; nothing else
    s = summarize(ev)
    assert {k for k, v in s.items() if v["is_demand"]} == {"pos_sale", "invoice_sale"}


def test_document_without_stock_movement_is_rejected():
    e = classify(1, 10, "2026-11-02", "A", D("1"), [Doc(1, "5102", "1", moves_stock=False)])
    assert e.event_type == "reject" and not e.is_demand
