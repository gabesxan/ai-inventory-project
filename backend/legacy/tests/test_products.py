"""DB-05 · product/unit normalization on FIXTURES (synthetic PRODUTOS rows)."""
from decimal import Decimal

from legacy.identity import SourceInstance
from legacy.products import canonical_unit, is_gtin, normalize_products, to_base

INST = SourceInstance(branch=1)


def row(id_, sku, unit="Un", pesado="0", barcode="7891000100103", name="ITEM", ativo="1", caixa="1"):
    return {"ID": str(id_), "CODIGO_INTERNO": sku, "DESCRICAO": name, "UNIDADE": unit, "PESADO": pesado,
            "CODIGO_BARRAS": barcode, "ATIVO": ativo, "UNIDADES_CAIXA": caixa, "GRUPO": "1", "DEPARTAMENTO": "2"}


def test_units_and_gtin():
    assert canonical_unit("Un  ") == "UN" and canonical_unit("Lt") == "L" and canonical_unit("Ce") is None
    assert is_gtin("7891000100103") and not is_gtin("0000000003066") and not is_gtin("123")


def test_packaged_sale_converts_only_with_known_ratio():
    [p] = normalize_products(INST, [row(1, "000001")])
    assert to_base(p, Decimal("2"), "CX", Decimal("12")).qty_base == Decimal("24")
    unknown = to_base(p, Decimal("2"), "CX", None)
    assert not unknown.ok and unknown.reason == "unknown_pack_ratio"
    assert not to_base(p, Decimal("2"), "CX", Decimal("0")).ok
    assert to_base(p, Decimal("3"), "Un", None).qty_base == Decimal("3")


def test_equivalent_totals_reconcile_in_base_units_and_unconvertible_rows_are_excluded():
    [p] = normalize_products(INST, [row(1, "000001")])
    lines = [(Decimal("2"), "CX", Decimal("6")), (Decimal("12"), "UN", None), (Decimal("1"), "FD", None)]
    conv = [to_base(p, q, u, r) for q, u, r in lines]
    trainable = [c for c in conv if c.ok]
    assert sum(c.qty_base for c in trainable) == Decimal("24")  # 2 boxes x 6 == 12 units, twice
    assert [c.reason for c in conv if not c.ok] == ["unknown_pack_ratio"]


def test_weighed_products_keep_precision_and_mismatched_units_do_not_convert():
    [kg] = normalize_products(INST, [row(2, "000002", unit="Kg", pesado="1")])
    assert to_base(kg, Decimal("0.735"), "KG").qty_base == Decimal("0.735")
    assert to_base(kg, Decimal("1"), "UN").reason == "unit_mismatch:UN->KG"


def test_quarantine_rules():
    ps = normalize_products(INST, [
        row(1, "000001"), row(2, "000001", barcode="7891000100110"),        # duplicate SKU
        row(3, "000003", unit="Ce", barcode="0"),                            # unknown unit
        row(4, "000004", unit="Un", pesado="1", barcode="0000000003066"),   # weighed count unit, internal code
    ])
    issues = {p.source_id: p.issues for p in ps}
    assert issues[1] == ["duplicate_sku"] and issues[2] == ["duplicate_sku"]
    assert issues[3] == ["unknown_unit"]
    assert issues[4] == ["weighed_count_unit"]
    assert ps[3].barcode is None and ps[3].source_code == "0000000003066"


def test_receipt_line_labelled_in_base_unit_uses_documented_units_per_box():
    # Real-data shape (DB-05): line says "UN" but QUANTIDADE counts boxes; I_UNIDADES_CAIXA = 12.
    [p] = normalize_products(INST, [row(1, "000001")])
    assert to_base(p, Decimal("2.0000"), "UN", Decimal("12")).qty_base == Decimal("24.0000")
    assert to_base(p, Decimal("2"), "UN", Decimal("12")).rule == "pack_ratio"
    assert to_base(p, Decimal("2"), "UN", Decimal("0")).reason == "invalid_ratio"
