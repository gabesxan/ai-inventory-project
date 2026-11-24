"""DB-12 · daily SKU series with coverage and availability evidence.

Day status (exactly one per product-day inside the series period):
  sale                    verified demand > 0 (DB-07 pos_sale + invoice_sale)
  true_zero               no demand, the ledger posted that day AND stock was known available
  zero_unknown_availability  no demand on a covered day, but availability is unknown
  known_stockout          availability evidence says no stock: censored, never calibration data
  unknown_quantity        the day has rows whose demand cannot be determined (rejected/unverified)
  calendar_gap            the store ledger posted nothing that day: missing, NOT zero

``uncensored`` (usable for uncensored demand calibration) is true only for ``sale`` and
``true_zero``. Every series carries its source period and the availability basis.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Set

UNCENSORED = {"sale", "true_zero"}


@dataclass(frozen=True)
class Day:
    day: str
    status: str
    demand: Optional[Decimal]      # None unless the quantity is known (sale / true_zero)
    receipts: Decimal
    available: Optional[bool]      # True / False / None (unknown)

    @property
    def uncensored(self) -> bool:
        return self.status in UNCENSORED


@dataclass
class Series:
    product_key: str
    warehouse_key: str
    period_start: str
    period_end: str
    source: str
    availability_basis: str
    days: List[Day]


def days_between(start: str, end: str) -> List[str]:
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    return [(d0 + timedelta(n)).isoformat() for n in range((d1 - d0).days + 1)]


def build_series(product_key: str, warehouse_key: str, period_start: str, period_end: str, source: str,
                 covered_days: Set[str], demand: Dict[str, Decimal], receipts: Dict[str, Decimal],
                 unknown_days: Iterable[str] = (), availability: Optional[Dict[str, bool]] = None,
                 availability_basis: str = "unknown") -> Series:
    """``availability`` maps day -> stock known available (True) / known out (False).
    A sale day is evidence of availability even when no balance is known."""
    unknown = set(unknown_days)
    availability = availability or {}
    out: List[Day] = []
    for d in days_between(period_start, period_end):
        rec = receipts.get(d, Decimal(0))
        av = availability.get(d)
        q = demand.get(d)
        if d not in covered_days:
            out.append(Day(d, "calendar_gap", None, rec, av))
        elif av is False:
            out.append(Day(d, "known_stockout", None, rec, False))
        elif d in unknown:
            out.append(Day(d, "unknown_quantity", None, rec, av))
        elif q is not None and q > 0:
            out.append(Day(d, "sale", q, rec, True))
        elif av is True:
            out.append(Day(d, "true_zero", Decimal(0), rec, True))
        else:
            out.append(Day(d, "zero_unknown_availability", None, rec, None))
    return Series(product_key, warehouse_key, period_start, period_end, source, availability_basis, out)


def calibration_demand(series: Series) -> List[Decimal]:
    """Uncensored observations only: sale and true_zero days."""
    return [d.demand for d in series.days if d.uncensored]
