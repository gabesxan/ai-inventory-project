"""DB-07 · classify legacy outbound movements; only verified sales count as demand.

Source facts (DB-07, real extract):
* ``ENTRADAS_SAIDAS`` is the stock ledger: one row per (branch, PDV 1, operation, product, day).
* ``V`` rows are the posted daily POS sales total; ticket-level ``VENDEDORES_VENDAS`` is a strict
  subset (every VV product-day exists in V), so V is the demand source, not VV.
* ``A``, ``D`` and ``_`` rows match outbound fiscal documents (``NOTAS_FISCAIS.S_TIPO='A'``) on
  product, day and quantity; the document's CFOP (national fiscal operation code) says what they are.
* ``P`` rows match internal outbound documents (``SAIDA_PRODUTOS`` type ``P``) whose meaning is not
  documented.

Event types (``is_demand`` only for the first two):
  pos_sale, invoice_sale, supplier_return, loss, warranty_exchange, internal_outbound,
  pending_document, canceled_document, transfer, unverified_outbound, sale_correction, reject
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, List, Optional, Sequence

SALE_CFOPS = {"5101", "5102", "5103", "5104", "5403", "5405", "6101", "6102", "6403", "6404", "6108"}
SUPPLIER_RETURN_CFOPS = {"5202", "6202", "5411", "6411"}
LOSS_CFOPS = {"5927"}
WARRANTY_CFOPS = {"5949", "6949"}  # natureza "TROCA GARANTIA" in this source
TRANSFER_CFOPS = {"5151", "5152", "5155", "6151", "6152", "6155", "5409", "6409"}
# NOTAS_FISCAIS.I_NFE_STATUS: 1 is the authorized/posted state (402 of 453 type-A documents).
# 0 and 3 are inferred as pending and canceled; neither counts as demand (unresolved meaning).
POSTED_STATUS = "1"
STATUS_EVENT = {"0": "pending_document", "3": "canceled_document"}

DEMAND = {"pos_sale", "invoice_sale"}


@dataclass(frozen=True)
class Doc:
    """An outbound fiscal document linked to a ledger row (type A in NOTAS_FISCAIS)."""
    doc_id: int
    cfop: Optional[str]
    status: Optional[str]
    moves_stock: bool = True


@dataclass(frozen=True)
class Event:
    movement_id: int
    product_id: int
    day: str
    qty: Decimal
    event_type: str
    reason: Optional[str] = None
    doc_ids: Sequence[int] = ()

    @property
    def is_demand(self) -> bool:
        return self.event_type in DEMAND


def _doc_class(d: Doc) -> str:
    c = (d.cfop or "").strip()[:4]
    if not d.moves_stock:
        return "reject"
    if d.status != POSTED_STATUS:
        return STATUS_EVENT.get(d.status or "", "pending_document")
    if c in SALE_CFOPS:
        return "invoice_sale"
    if c in SUPPLIER_RETURN_CFOPS:
        return "supplier_return"
    if c in LOSS_CFOPS:
        return "loss"
    if c in WARRANTY_CFOPS:
        return "warranty_exchange"
    if c in TRANSFER_CFOPS:
        return "transfer"
    return "unverified_outbound"


def classify(movement_id: int, product_id: int, day: str, op: str, qty: Decimal,
             docs: Iterable[Doc] = (), internal_doc: bool = False) -> Event:
    """Classify one ledger outbound row. ``docs`` are the fiscal documents proven to match it
    (same product and day, line quantities in base units summing to ``qty``)."""
    docs = list(docs)
    ids = tuple(d.doc_id for d in docs)
    if qty == 0:
        return Event(movement_id, product_id, day, qty, "reject", "zero_quantity", ids)
    if op == "V":
        if qty < 0:
            return Event(movement_id, product_id, day, qty, "sale_correction", "negative_sale_total")
        return Event(movement_id, product_id, day, qty, "pos_sale")
    if op == "P":
        if internal_doc:
            return Event(movement_id, product_id, day, qty, "internal_outbound", "saida_produtos_type_P_meaning_unresolved")
        return Event(movement_id, product_id, day, qty, "unverified_outbound", "no_matching_internal_document")
    if op in ("A", "D", "_"):
        if not docs:
            return Event(movement_id, product_id, day, qty, "unverified_outbound", "no_matching_fiscal_document")
        classes = {_doc_class(d) for d in docs}
        if len(classes) > 1:
            return Event(movement_id, product_id, day, qty, "unverified_outbound", "ambiguous_documents:" + ",".join(sorted(classes)), ids)
        cls = classes.pop()
        return Event(movement_id, product_id, day, qty, cls, None if cls != "reject" else "document_without_stock_movement", ids)
    return Event(movement_id, product_id, day, qty, "reject", f"not_outbound_op:{op}")


def demand_total(events: Iterable[Event]) -> Decimal:
    return sum((e.qty for e in events if e.is_demand), Decimal(0))


def summarize(events: List[Event]) -> dict:
    out: dict = {}
    for e in events:
        s = out.setdefault(e.event_type, {"rows": 0, "qty": Decimal(0), "is_demand": e.is_demand})
        s["rows"] += 1
        s["qty"] += e.qty
    return out
