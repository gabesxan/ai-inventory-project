"""DB-08 · returns and corrections on FIXTURES."""
from decimal import Decimal as D

from legacy.returns import Return, Sale, net_sales

SALES = [Sale("s1", 10, "2026-11-02", D("5")), Sale("s2", 11, "2026-11-02", D("1.250"))]


def test_partial_return_reduces_net_sales_only_once():
    r = Return("r1", 10, "2026-11-04", D("2"), "s1", "fixture NF 1202")
    once = net_sales(SALES, [r])
    twice = net_sales(SALES, [r, r])                    # same return delivered twice
    assert (once.gross, once.returns, once.net) == (D("6.250"), D("2"), D("4.250"))
    assert (twice.returns, twice.net) == (D("2"), D("4.250")) and twice.applied == ["r1"]
    assert r.signed_delta == D("-2")


def test_return_beyond_the_original_is_capped_and_flagged():
    res = net_sales(SALES, [Return("r1", 10, "2026-11-04", D("2"), "s1", "x"), Return("r2", 10, "2026-11-05", D("4"), "s1", "x")])
    assert res.returns == D("5") and res.net == D("1.250")
    assert {"return_id": "r2", "effective_date": "2026-11-05", "flag": "exceeds_original", "excess": "1"} in res.flagged


def test_unlinked_correction_stays_traceable_with_effective_date_and_flag():
    c = Return("ledger/mov/123", 11, "2026-11-07", D("0.500"), None, "ENTRADAS_SAIDAS V", "negative_daily_total")
    res = net_sales(SALES, [c])
    assert res.net == D("5.750")
    assert res.flagged == [{"return_id": "ledger/mov/123", "effective_date": "2026-11-07", "flag": "negative_daily_total",
                            "qty": "0.500", "source": "ENTRADAS_SAIDAS V"}]
