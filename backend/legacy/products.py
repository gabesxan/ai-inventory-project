"""DB-05 · normalize legacy product and unit records for the v1 catalog.

Input: the DB-04 extract (``PRODUTOS``, ``CAD_UNIDADES``). Output: staged product records keyed
by the DB-03 stable key, plus a quarantine list. Nothing here writes to a database.

Rules
* SKU = ``CODIGO_INTERNO`` (trimmed); name = ``DESCRICAO`` (trimmed); barcode = ``CODIGO_BARRAS``
  only when it is a valid GTIN-8/12/13/14 (check digit), otherwise kept as ``source_code`` only.
* Stock (base) unit = ``PRODUTOS.UNIDADE`` mapped through ``UNIT_MAP``. Quantities stay
  ``Decimal`` at the source scale; nothing is rounded here.
* Package conversions happen ONLY with a known ratio (``to_base``). A quantity in another unit
  without a documented positive ratio is unconvertible and must not enter training.
* Quarantine (not imported, not trained): unknown unit, duplicate SKU, duplicate barcode,
  weighed flag that contradicts a count unit, and an empty SKU or name.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from legacy.identity import SourceInstance, product_key

NULL = "\\N"

# Source unit spelling (trimmed, upper-case) -> canonical v1 unit and its kind.
UNIT_MAP: Dict[str, tuple] = {
    "UN": ("UN", "count"), "UND": ("UN", "count"), "UNID": ("UN", "count"), "PC": ("UN", "count"),
    "KG": ("KG", "mass"), "G": ("G", "mass"),
    "LT": ("L", "volume"), "L": ("L", "volume"), "ML": ("ML", "volume"),
    "MT": ("M", "length"), "M": ("M", "length"),
}
# Package units: never equal to a base unit; they need a per-line or per-product ratio.
PACKAGE_UNITS = {"CX", "FD", "FDO", "PCT", "PT", "DZ", "SC", "BD", "GF", "LA", "CJ", "KIT", "DP", "PAC"}


def clean(v: Optional[str]) -> Optional[str]:
    if v is None or v == NULL:
        return None
    v = v.strip()
    return v or None


def canonical_unit(raw: Optional[str]) -> Optional[str]:
    u = clean(raw)
    return UNIT_MAP[u.upper()][0] if u and u.upper() in UNIT_MAP else None


def is_gtin(code: Optional[str]) -> bool:
    c = clean(code)
    if not c or not c.isdigit() or len(c) not in (8, 12, 13, 14) or set(c) == {"0"}:
        return False
    digits = [int(x) for x in c]
    body, check = digits[:-1], digits[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


@dataclass
class StagedProduct:
    key: str
    source_id: int
    sku: Optional[str]
    name: Optional[str]
    unit: Optional[str]
    unit_kind: Optional[str]
    source_unit: Optional[str]
    weighed: bool
    active: bool
    barcode: Optional[str]
    source_code: Optional[str]
    units_per_pack: Optional[int]
    group_id: Optional[int]
    department_id: Optional[int]
    issues: List[str] = field(default_factory=list)

    @property
    def quarantined(self) -> bool:
        return bool(self.issues)


def _int(v: Optional[str]) -> Optional[int]:
    v = clean(v)
    return int(v) if v is not None else None


def normalize_products(inst: SourceInstance, rows: Iterable[Dict[str, str]]) -> List[StagedProduct]:
    out: List[StagedProduct] = []
    for r in rows:
        su = clean(r["UNIDADE"])
        unit = canonical_unit(su)
        kind = UNIT_MAP[su.upper()][1] if unit else None
        weighed = clean(r["PESADO"]) == "1"
        code = clean(r["CODIGO_BARRAS"])
        p = StagedProduct(
            key=product_key(inst, int(r["ID"])), source_id=int(r["ID"]),
            sku=clean(r["CODIGO_INTERNO"]), name=clean(r["DESCRICAO"]),
            unit=unit, unit_kind=kind, source_unit=su, weighed=weighed,
            active=clean(r["ATIVO"]) == "1",
            barcode=code if is_gtin(code) else None, source_code=code,
            units_per_pack=_int(r.get("UNIDADES_CAIXA")),
            group_id=_int(r.get("GRUPO")), department_id=_int(r.get("DEPARTAMENTO")),
        )
        if not p.sku:
            p.issues.append("empty_sku")
        if not p.name:
            p.issues.append("empty_name")
        if unit is None:
            p.issues.append("unknown_unit")
        elif weighed and kind == "count":
            p.issues.append("weighed_count_unit")
        out.append(p)
    for attr, issue in (("sku", "duplicate_sku"), ("barcode", "duplicate_barcode")):
        counts = Counter(getattr(p, attr).upper() for p in out if getattr(p, attr))
        for p in out:
            v = getattr(p, attr)
            if v and counts[v.upper()] > 1:
                p.issues.append(issue)
    return out


@dataclass(frozen=True)
class Conversion:
    qty_base: Optional[Decimal]
    rule: str  # same_unit | pack_ratio | unconvertible
    reason: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.qty_base is not None


def to_base(product: StagedProduct, qty: Decimal, unit_raw: Optional[str],
            ratio: Optional[Decimal] = None) -> Conversion:
    """Convert a quantity to the product's base unit.

    ``ratio`` is the documented number of base units per one recorded unit, e.g. the receipt
    line's ``I_UNIDADES_CAIXA``. DB-05 verified it on real data: entry-line QUANTIDADE x
    I_UNIDADES_CAIXA equals the source's own stock entry (ENTRADAS_SAIDAS 'C') on 99.7% of
    product-days, even when the line is labelled with the product's own unit. Rules:

    * label is the product's unit or a package unit, ratio given and > 0 -> qty * ratio
    * label is the product's unit, no ratio -> qty (same unit)
    * package label without a positive ratio -> unconvertible (unknown_pack_ratio)
    * label of another unit (e.g. UN on a KG product) -> unconvertible, never guessed
    """
    if product.unit is None:
        return Conversion(None, "unconvertible", "product_unit_unknown")
    u = clean(unit_raw)
    same = u is None or canonical_unit(u) == product.unit
    pack = u is not None and u.upper() in PACKAGE_UNITS
    if not (same or pack):
        return Conversion(None, "unconvertible", f"unit_mismatch:{u.upper()}->{product.unit}")
    if ratio is not None:
        if ratio <= 0:
            return Conversion(None, "unconvertible", "invalid_ratio")
        return Conversion(qty * ratio, "same_unit" if ratio == 1 else "pack_ratio")
    if pack:
        return Conversion(None, "unconvertible", "unknown_pack_ratio")
    return Conversion(qty, "same_unit")
