"""DB-11 · purchase-order arrivals, outstanding pipeline and measured lead times.

Real source (DB-11): ``PEDIDOS``/``ITENS_PEDIDO`` are EMPTY and no entry NF carries
``NUMERO_PEDIDO``, so there is no documented order->receipt key. The pipeline and observed lead
times are therefore UNAVAILABLE (never zero). NF emission-to-entry gaps are transit times, not
order lead times, and are not used.

The logic below is what a source with orders must satisfy (fixture-tested):
* receipts reduce an order line's outstanding quantity only through a documented link;
* outstanding never goes below zero (over-receipt is flagged); cancellations close the remainder;
* outstanding is bucketed by due date relative to an as-of date;
* a lead time is measured only from a verified (order date, receipt date) pair; a missing order
  date leaves it null.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

UNAVAILABLE = "unavailable"


@dataclass
class OrderLine:
    line_id: str
    product_id: int
    supplier_id: int
    ordered: Decimal
    order_date: Optional[str]
    due_date: Optional[str]
    canceled: bool = False
    received: Decimal = Decimal(0)
    receipts: List[tuple] = field(default_factory=list)   # (receipt_id, day, qty)
    flags: List[str] = field(default_factory=list)

    @property
    def outstanding(self) -> Decimal:
        if self.canceled:
            return Decimal(0)
        return max(self.ordered - self.received, Decimal(0))


@dataclass(frozen=True)
class Receipt:
    receipt_id: str
    order_line_id: Optional[str]   # documented key; None = not linkable
    day: str
    qty: Decimal


def apply_receipts(lines: Iterable[OrderLine], receipts: Iterable[Receipt]) -> Dict[str, OrderLine]:
    by_id = {l.line_id: l for l in lines}
    seen = set()
    for r in receipts:
        if r.receipt_id in seen or r.order_line_id is None or r.order_line_id not in by_id:
            continue
        seen.add(r.receipt_id)
        l = by_id[r.order_line_id]
        l.received += r.qty
        l.receipts.append((r.receipt_id, r.day, r.qty))
        if l.received > l.ordered:
            l.flags.append("over_receipt")
    return by_id


def bucket(due: Optional[str], as_of: str) -> str:
    if due is None:
        return "no_due_date"
    days = (date.fromisoformat(due) - date.fromisoformat(as_of)).days
    if days < 0:
        return "overdue"
    if days <= 7:
        return "due_0_7"
    if days <= 30:
        return "due_8_30"
    return "due_31_plus"


def pipeline(lines: Optional[Iterable[OrderLine]], as_of: str):
    """Outstanding by due-date bucket, or UNAVAILABLE when the source has no orders."""
    if lines is None:
        return UNAVAILABLE
    out: Dict[str, Decimal] = {}
    for l in lines:
        if l.outstanding > 0:
            b = bucket(l.due_date, as_of)
            out[b] = out.get(b, Decimal(0)) + l.outstanding
    return out


def lead_times(lines: Iterable[OrderLine]) -> List[Optional[int]]:
    """Days from order to FIRST linked receipt; None when the order date is missing."""
    out = []
    for l in lines:
        if not l.receipts:
            continue
        first = min(d for _, d, _ in l.receipts)
        out.append(None if l.order_date is None else (date.fromisoformat(first) - date.fromisoformat(l.order_date)).days)
    return out
