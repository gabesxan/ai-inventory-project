"""DB-09 · stock receipts and cost provenance.

Source facts (DB-05/DB-09, real extract):
* The posted stock effect of an entry is the ledger row ``ENTRADAS_SAIDAS`` ``C`` (per product, day).
* Entry documents are ``NOTAS_FISCAIS.S_TIPO='E'`` with lines in purchase packs:
  base qty = ``QUANTIDADE x I_UNIDADES_CAIXA`` (DB-05, 99.7% equal to the ledger).
* ``VALOR_UNITARIO`` (scale 4) is the price per purchase unit; ``F_VALOR_TOTAL`` = qty x price.
* ``F_CUSTO_PRODUTO_UNIT`` (scale 3) is a cost per BASE unit recorded by the source: equal to
  price / units-per-box on 60,011 lines and higher on 83,718 (taxes/freight inferred, unresolved).
* The line CFOP (national code) separates supplier purchases from bonus goods, use/consumption,
  services, transfers, returns and other entries.

A receipt enters stock history only when the ledger shows the stock effect; a document without
it (canceled or never posted) is kept as ``no_stock_effect`` and never adds quantity.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

# CFOP digits 2-4 (first digit 1 = in-state, 2 = interstate, 3 = import).
CLASS_BY_CFOP_SUFFIX = {
    "101": "supplier_purchase", "102": "supplier_purchase", "401": "supplier_purchase",
    "403": "supplier_purchase", "117": "supplier_purchase", "118": "supplier_purchase",
    "910": "supplier_bonus", "911": "supplier_bonus",
    "151": "transfer_in", "152": "transfer_in", "409": "transfer_in",
    "201": "customer_return", "202": "customer_return", "410": "customer_return", "411": "customer_return",
    "556": "use_consumption", "407": "use_consumption", "551": "fixed_asset",
    "933": "service", "253": "utility", "653": "fuel_consumption",
    "949": "other_entry",
}
STOCK_RECEIPT_CLASSES = {"supplier_purchase", "supplier_bonus"}  # supplier receipts proper


def classify_cfop(cfop: Optional[str]) -> str:
    c = (cfop or "").strip()
    if len(c) != 4 or not c.isdigit() or c[0] not in "123":
        return "unknown_cfop"
    return CLASS_BY_CFOP_SUFFIX.get(c[1:], "unknown_cfop")


COST_Q = Decimal("0.000001")  # derived per-base-unit price keeps 6 decimals (source price has 4)


@dataclass(frozen=True)
class ReceiptCost:
    price_per_purchase_unit: Optional[Decimal]   # VALOR_UNITARIO, as recorded (scale 4)
    units_per_purchase_unit: Optional[int]       # I_UNIDADES_CAIXA
    invoice_cost_per_base_unit: Optional[Decimal]  # derived: price / units, quantized to 6 dp
    recorded_cost_per_base_unit: Optional[Decimal]  # F_CUSTO_PRODUTO_UNIT, as recorded (scale 3)
    cost_status: str  # known | explicit_zero | unknown


def receipt_cost(price: Optional[Decimal], units: Optional[int], recorded: Optional[Decimal]) -> ReceiptCost:
    """Keep explicit zero as zero and unknown as None; never invent a cost."""
    if price is None:
        return ReceiptCost(None, units, None, recorded, "unknown")
    derived = (price / units).quantize(COST_Q) if units and units > 0 else None
    status = "explicit_zero" if price == 0 else ("known" if derived is not None else "unknown")
    return ReceiptCost(price, units, derived, recorded, status)
