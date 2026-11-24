"""DB-13 · staged history rows: one reader shared by the import preview and the DB-02 loader.

Inputs are the staged outputs of earlier cards (outside Git):
* DB-05 ``products.csv``: product key, source id, SKU and base unit; ``issues`` marks quarantined products.
* DB-07 ``events.csv``: ledger outbound events. They already hold the NET daily sales and the 18
  negative-day corrections (``sale_correction``), so DB-08's ticket-level ``corrections.csv`` is NOT
  read here: applying it again would double count (see docs/data/DB-08-returns-and-corrections.md).
* DB-09 ``stock_receipts.csv`` (one row per product, day and unit) and, for the unit cost,
  ``receipt_lines.csv``.

Rules
* Quantities are base units. ``quantity`` is >= 0 and ``signed_quantity`` keeps the direction.
* ``stock_availability`` is ``available`` only on a sale (positive evidence, DB-12). Everything else is
  ``unknown``. There is no opening stock, so nothing is ever inferred as a stockout or as zero demand.
* A row that cannot be staged becomes a :class:`Rejection` with a row-safe reason code and its
  one-based file line. Source values never appear in a reason.

Stdlib only (Python 3.9+).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Iterator, Optional, Tuple, Union

from legacy.identity import SourceInstance

csv.field_size_limit(10_000_000)

# Event class per DB-07 event type. ``reject`` is absent on purpose: see NOT_STAGED.
EVENT_CLASS = {
    "pos_sale": "sale",
    "invoice_sale": "sale",
    "sale_correction": "return",
    "supplier_return": "return",
    "loss": "other_outbound",
    "warranty_exchange": "other_outbound",
    "internal_outbound": "other_outbound",
    "pending_document": "other_outbound",
    "canceled_document": "other_outbound",
    "transfer": "other_outbound",
    "unverified_outbound": "other_outbound",
    "receipt": "receipt",
}
# DB-07 ``reject``: a ledger row whose document does not move stock.
NOT_STAGED = {"reject": "document_does_not_move_stock"}
AVAILABLE_ON = {"pos_sale", "invoice_sale"}

REASONS = (
    "missing_record_key", "unknown_product", "product_unknown_unit", "invalid_date", "invalid_quantity",
    "unknown_event_type", "document_does_not_move_stock", "receipt_quantity_unavailable",
    "product_not_in_catalog",
)


@dataclass(frozen=True)
class StagedInputs:
    products: Path
    events: Path
    receipts: Path
    receipt_lines: Optional[Path] = None
    series_index: Optional[Path] = None   # DB-12 per-series coverage summary
    series: Optional[Path] = None         # DB-12 day-level series (.csv.gz)

    @classmethod
    def from_out_dir(cls, out: Path) -> "StagedInputs":
        def opt(p: Path) -> Optional[Path]:
            return p if p.is_file() else None
        return cls(out / "db05" / "products.csv", out / "db07" / "events.csv", out / "db09" / "stock_receipts.csv",
                   opt(out / "db09" / "receipt_lines.csv"), opt(out / "db12" / "series_index.csv"),
                   opt(out / "db12" / "series.csv.gz"))


@dataclass(frozen=True)
class HistoryRow:
    record_id: str
    warehouse_key: str
    product_key: str
    sku: str
    event_date: str
    event_type: str
    event_class: str
    is_demand: bool
    quantity: Decimal
    signed_quantity: Decimal
    unit: str
    unit_cost: Optional[Decimal]
    stock_availability: str


@dataclass(frozen=True)
class Rejection:
    dataset: str
    line_number: Optional[int]
    reason: str
    record_key: Optional[str] = None


Item = Union[HistoryRow, Rejection]


def _decimal(v: Optional[str]) -> Optional[Decimal]:
    try:
        d = Decimal((v or "").strip())
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def _day(v: Optional[str]) -> Optional[str]:
    try:
        return date.fromisoformat((v or "").strip()).isoformat()
    except ValueError:
        return None


def _dict_rows(path: Path) -> Iterator[Tuple[int, Dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield reader.line_num, row


def load_products(path: Path) -> Dict[int, Dict[str, str]]:
    return {int(r["source_id"]): r for _, r in _dict_rows(path)}


def receipt_costs(path: Optional[Path]) -> Dict[Tuple[int, str], Decimal]:
    """Quantity-weighted invoice cost per base unit for each (product, day), posted known lines only."""
    if path is None:
        return {}
    num: Dict[Tuple[int, str], Decimal] = {}
    den: Dict[Tuple[int, str], Decimal] = {}
    for _, r in _dict_rows(path):
        qty, cost = _decimal(r["qty_base"]), _decimal(r["invoice_cost_per_base_unit"])
        if r["status"] != "posted" or r["cost_status"] != "known" or not qty or qty <= 0 or cost is None or cost < 0:
            continue
        k = (int(r["product_id"]), r["day"])
        num[k] = num.get(k, Decimal(0)) + qty * cost
        den[k] = den.get(k, Decimal(0)) + qty
    return {k: (num[k] / den[k]).quantize(Decimal("0.000001")) for k in num}


def _product_problem(products: Dict[int, Dict[str, str]], raw_id: str) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    try:
        p = products.get(int(raw_id))
    except ValueError:
        p = None
    if p is None:
        return None, "unknown_product"
    if p["issues"]:
        return None, "product_unknown_unit" if "unit" in p["issues"] else "unknown_product"
    return p, None


def read_history(staged: StagedInputs, inst: SourceInstance, warehouse_key: str) -> Iterator[Item]:
    """Yield every staged event, then every receipt, as a HistoryRow or an attributable Rejection."""
    products = load_products(staged.products)
    for line, r in _dict_rows(staged.events):
        key = (r["movement_key"] or "").strip()
        if not key:
            yield Rejection("events", line, "missing_record_key")
            continue
        etype = r["event_type"]
        if etype in NOT_STAGED:
            yield Rejection("events", line, NOT_STAGED[etype], key)
            continue
        if etype not in EVENT_CLASS:
            yield Rejection("events", line, "unknown_event_type", key)
            continue
        p, why = _product_problem(products, r["product_id"])
        if why:
            yield Rejection("events", line, why, key)
            continue
        day, qty = _day(r["day"]), _decimal(r["qty"])
        if day is None:
            yield Rejection("events", line, "invalid_date", key)
            continue
        if qty is None:
            yield Rejection("events", line, "invalid_quantity", key)
            continue
        yield HistoryRow(
            record_id=key, warehouse_key=warehouse_key, product_key=p["key"], sku=p["sku"], event_date=day,
            event_type=etype, event_class=EVENT_CLASS[etype], is_demand=r["is_demand"] == "1",
            quantity=abs(qty), signed_quantity=qty, unit=p["unit"], unit_cost=None,
            stock_availability="available" if etype in AVAILABLE_ON else "unknown")

    costs = receipt_costs(staged.receipt_lines)
    for line, r in _dict_rows(staged.receipts):
        key = f"{inst.tag}/receipt/{r['product_id']}/{r['day']}/{r['unit']}"
        p, why = _product_problem(products, r["product_id"])
        if why:
            yield Rejection("receipts", line, why, key)
            continue
        day, qty = _day(r["day"]), _decimal(r["qty_base"])
        if day is None:
            yield Rejection("receipts", line, "invalid_date", key)
            continue
        if qty is None or qty <= 0:
            # a ledger entry without its fiscal document has no resolvable base quantity (DB-09)
            unresolved = r["provenance"] == "ledger_without_document" and qty == 0
            yield Rejection("receipts", line, "receipt_quantity_unavailable" if unresolved else "invalid_quantity", key)
            continue
        yield HistoryRow(
            record_id=key, warehouse_key=warehouse_key, product_key=p["key"], sku=p["sku"], event_date=day,
            event_type="receipt", event_class="receipt", is_demand=False, quantity=qty, signed_quantity=qty,
            unit=r["unit"] or p["unit"], unit_cost=costs.get((int(r["product_id"]), day)),
            stock_availability="unknown")


__all__ = ["EVENT_CLASS", "REASONS", "HistoryRow", "Rejection", "StagedInputs", "read_history"]
