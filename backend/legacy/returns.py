"""DB-08 · returns, reversals and corrections with signed deltas and explicit links.

Source facts (DB-08, real extract)
* Ledger ``ENTRADAS_SAIDAS`` V is a DAILY NET total: gross and returns cannot be separated there.
  Negative daily totals (18) are unlinked corrections.
* Ticket lines (``VENDEDORES_VENDAS``, a subset) show reversals: a negative line on the same coupon
  and product as a positive line is a PROVEN link (item cancellation, 1,520 cases); a negative line
  with no positive line on its coupon is an unmatched credit (68).
* Customer-return NFs (entry CFOP x201/x202/x411) carry no reference to the original sale: unlinked.
* Supplier returns (type A, CFOP x202) carry ``S_CHAVE_NFE_DEVOLUCAO`` = the original entry NF's
  access key: a proven link on the purchase side (not sales).

``net_sales`` applies each return exactly once (by its id), caps a linked return at what remains of
its original line, and flags anything it cannot apply cleanly.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class Sale:
    sale_id: str
    product_id: int
    day: str
    qty: Decimal


@dataclass(frozen=True)
class Return:
    return_id: str
    product_id: int
    effective_date: str
    qty: Decimal                    # magnitude returned (> 0)
    original_sale_id: Optional[str]  # set only when the source proves the link
    source: str
    flag: Optional[str] = None       # quality flag for unlinked or odd records

    @property
    def signed_delta(self) -> Decimal:
        return -self.qty


@dataclass
class NetResult:
    gross: Decimal
    returns: Decimal
    net: Decimal
    applied: List[str]
    flagged: List[Dict]


def net_sales(sales: Iterable[Sale], returns: Iterable[Return]) -> NetResult:
    sales = list(sales)
    remaining = {s.sale_id: s.qty for s in sales}
    gross = sum((s.qty for s in sales), Decimal(0))
    seen, applied, flagged = set(), [], []
    total = Decimal(0)
    for r in returns:
        if r.return_id in seen:
            continue  # the same return is never counted twice
        seen.add(r.return_id)
        if r.qty <= 0:
            flagged.append({"return_id": r.return_id, "effective_date": r.effective_date, "flag": "non_positive_return"})
            continue
        if r.original_sale_id is None:
            total += r.qty
            applied.append(r.return_id)
            flagged.append({"return_id": r.return_id, "effective_date": r.effective_date,
                            "flag": r.flag or "unlinked_credit", "qty": str(r.qty), "source": r.source})
            continue
        left = remaining.get(r.original_sale_id)
        if left is None:
            flagged.append({"return_id": r.return_id, "effective_date": r.effective_date, "flag": "original_not_found"})
            continue
        take = min(left, r.qty)
        remaining[r.original_sale_id] = left - take
        total += take
        applied.append(r.return_id)
        if take < r.qty:
            flagged.append({"return_id": r.return_id, "effective_date": r.effective_date, "flag": "exceeds_original",
                            "excess": str(r.qty - take)})
    return NetResult(gross, total, gross - total, applied, flagged)
