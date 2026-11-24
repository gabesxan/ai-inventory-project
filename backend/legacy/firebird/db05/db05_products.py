"""DB-05 · normalize products on the real extract and verify unit/pack ratios.

    PYTHONPATH=. python3 legacy/firebird/db05/db05_products.py <extract_dir> <out_dir>

Writes staged products, the quarantine list and summary.json to <out_dir> (outside Git).
Prints only aggregate evidence.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from legacy.extract import Extract, dec, num, val
from legacy.identity import SourceInstance
from legacy.products import PACKAGE_UNITS, canonical_unit, normalize_products, to_base


def main(extract_dir: str, out_dir: str) -> dict:
    ex = Extract(Path(extract_dir))
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    inst = SourceInstance(branch=ex.scope["branch"])
    res: dict = {"extract": str(ex.path), "snapshot_fbk_sha256": ex.manifest["source"]["snapshot_fbk_sha256"]}

    prods = normalize_products(inst, ex.rows("PRODUTOS"))
    by_id = {p.source_id: p for p in prods}
    res["products"] = {
        "rows": len(prods),
        "staged_ok": sum(1 for p in prods if not p.quarantined),
        "quarantined": sum(1 for p in prods if p.quarantined),
        "issues": dict(Counter(i for p in prods for i in p.issues)),
        "by_unit": dict(Counter((p.source_unit, p.unit, p.weighed) for p in prods).most_common()),
        "valid_gtin_barcodes": sum(1 for p in prods if p.barcode),
        "internal_codes_not_gtin": sum(1 for p in prods if p.source_code and not p.barcode),
        "units_per_pack_gt1": sum(1 for p in prods if (p.units_per_pack or 1) > 1),
    }
    res["products"]["by_unit"] = {f"{k[0]}->{k[1]} weighed={k[2]}": v for k, v in res["products"]["by_unit"].items()}
    res["cad_unidades"] = sorted({(val(r["UNIDADE"]) or "") for r in ex.rows("CAD_UNIDADES")})

    # --- NF line units vs product base unit ----------------------------------
    hdr = {int(r["ID"]): r for r in ex.rows("NOTAS_FISCAIS")}
    line_units = Counter()
    conv_rules = Counter()
    nf_base = defaultdict(lambda: defaultdict(Decimal))  # candidate -> (prod, date) -> qty
    orphan = 0
    for r in ex.rows("ITENS_NOTA_FISCAL"):
        pid = int(r["ID_PRODUTO"])
        p = by_id.get(pid)
        u = (val(r["S_UNIDADE_MEDIDA"]) or "").upper()
        if p is None:
            orphan += 1
            continue
        line_units[(u, p.unit)] += 1
        h = hdr[int(r["ID_NOTA_FISCAL"])]
        if val(h["S_TIPO"]) != "E":
            continue
        q = dec(r["QUANTIDADE"])
        caixa = num(r["I_UNIDADES_CAIXA"])
        fator = dec(r["F_FATOR_CONVERSAO"])
        c = to_base(p, q, u, Decimal(caixa) if caixa is not None else None)
        conv_rules[c.rule if c.ok else c.reason] += 1
        d = val(h["DATA_SAIDA_ENTRADA"])
        key = (pid, d)
        nf_base["qty"][key] += q
        nf_base["qty_x_units_per_box"][key] += q * (caixa if caixa and caixa > 0 else 1)
        nf_base["qty_x_factor"][key] += q * (fator if fator and fator > 0 else 1)
        if c.ok:
            nf_base["to_base"][key] += c.qty_base
    res["nf_lines"] = {
        "missing_product_skipped": orphan,
        "unit_pairs_line_to_product": {f"{a or '-'}->{b}": n for (a, b), n in line_units.most_common(15)},
        "entry_line_conversion": dict(conv_rules),
    }

    # --- the source's own stock effect: ENTRADAS_SAIDAS 'C' rows -------------
    es_c = defaultdict(Decimal)
    first_c = None
    for r in ex.rows("ENTRADAS_SAIDAS"):
        if val(r["S_OPERACAO"]) == "C":
            es_c[(int(r["ID_PRODUTO"]), r["D_DATA"])] += dec(r["F_QUANTIDADE"])
            first_c = min(first_c or r["D_DATA"], r["D_DATA"])
    comparable = [k for k in nf_base["qty"] if k[1] and k[1] >= first_c]
    rec = {}
    for cand in ("qty", "qty_x_units_per_box", "qty_x_factor", "to_base"):
        keys = [k for k in comparable if k in nf_base[cand]]
        match = sum(1 for k in keys if k in es_c and es_c[k] == nf_base[cand][k])
        rec[cand] = {"product_days": len(keys), "equal_to_C_movements": match}
    res["receipt_reconciliation"] = {
        "es_c_first_date": first_c,
        "nf_entry_product_days_since_then": len(comparable),
        "product_days_with_C_movement": sum(1 for k in comparable if k in es_c),
        "candidates": rec,
    }

    # --- sales: recorded in the product's stock unit (no unit/ratio columns) --------
    frac = Counter()
    elig = Counter()
    frac_count_products = set()
    for r in ex.rows("ENTRADAS_SAIDAS"):
        if val(r["S_OPERACAO"]) != "V":
            continue
        p = by_id.get(int(r["ID_PRODUTO"]))
        q = dec(r["F_QUANTIDADE"])
        is_frac = q != q.to_integral_value()
        kind = p.unit_kind if p else "missing"
        frac[(kind, p.weighed if p else None, is_frac)] += 1
        if p is None:
            elig["excluded_missing_product"] += 1
        elif p.quarantined:
            elig["excluded_quarantined_product"] += 1
        else:
            c = to_base(p, q, p.source_unit)
            elig["eligible_base_units" if c.ok else "excluded_" + (c.reason or "")] += 1
            if is_frac and p.unit_kind == "count":
                frac_count_products.add(p.source_id)
    res["sales_fractional_by_kind"] = {f"{k[0]} weighed={k[1]} fractional={k[2]}": n for k, n in sorted(frac.items(), key=str)}
    res["sales_training_eligibility"] = dict(elig)
    res["count_unit_products_with_fractional_sales"] = len(frac_count_products)
    res["receipt_line_training_eligibility"] = dict(conv_rules)

    with (out / "products.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["key", "source_id", "sku", "name", "unit", "source_unit", "weighed", "active", "barcode",
                    "units_per_pack", "group_id", "department_id", "issues"])
        for p in prods:
            w.writerow([p.key, p.source_id, p.sku, p.name, p.unit, p.source_unit, int(p.weighed), int(p.active),
                        p.barcode or "", p.units_per_pack, p.group_id, p.department_id, ";".join(p.issues)])
    (out / "summary.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), indent=2, ensure_ascii=False, default=str))
