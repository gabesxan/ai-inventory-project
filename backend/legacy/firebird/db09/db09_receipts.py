"""DB-09 · receipts with cost provenance on the real extract; reconcile by month and unit.

    PYTHONPATH=. python3 legacy/firebird/db09/db09_receipts.py <extract_dir> <out_dir>

Writes receipt_lines.csv, stock_receipts.csv and summary.json to <out_dir> (outside Git).
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from legacy.extract import Extract, dec, num, val
from legacy.identity import SourceInstance, movement_key, nf_key, nf_line_key, supplier_key
from legacy.products import normalize_products, to_base
from legacy.receipts import STOCK_RECEIPT_CLASSES, classify_cfop, receipt_cost


def main(extract_dir: str, out_dir: str) -> dict:
    ex = Extract(Path(extract_dir))
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    inst = SourceInstance(branch=ex.scope["branch"])
    prods = {p.source_id: p for p in normalize_products(inst, ex.rows("PRODUTOS"))}
    hdr = {int(r["ID"]): r for r in ex.rows("NOTAS_FISCAIS") if val(r["S_TIPO"]) == "E"}

    ledger = defaultdict(Decimal)
    ledger_ids = defaultdict(list)
    for r in ex.rows("ENTRADAS_SAIDAS"):
        if val(r["S_OPERACAO"]) == "C":
            k = (int(r["ID_PRODUTO"]), r["D_DATA"])
            ledger[k] += dec(r["F_QUANTIDADE"])
            ledger_ids[k].append(int(r["ID"]))
    ledger_start = min(k[1] for k in ledger)

    lines = defaultdict(list)
    line_status = Counter()
    cost_status = Counter()
    classes = Counter()
    for r in ex.rows("ITENS_NOTA_FISCAL"):
        h = hdr.get(int(r["ID_NOTA_FISCAL"]))
        if h is None:
            continue
        pid = int(r["ID_PRODUTO"])
        p = prods.get(pid)
        caixa = num(r["I_UNIDADES_CAIXA"])
        conv = to_base(p, dec(r["QUANTIDADE"]), val(r["S_UNIDADE_MEDIDA"]), Decimal(caixa) if caixa is not None else None) if p else None
        cls = classify_cfop(val(r["S_CFOP"]))
        cost = receipt_cost(dec(r["VALOR_UNITARIO"]), caixa, dec(r["F_CUSTO_PRODUTO_UNIT"]))
        classes[cls] += 1
        cost_status[cost.cost_status] += 1
        day = val(h["DATA_SAIDA_ENTRADA"])
        rec = {
            "line_key": nf_line_key(inst, int(r["ID"])), "doc_key": nf_key(inst, int(h["ID"])),
            "supplier_key": supplier_key(inst, int(h["ID_FORNECEDOR"])) if val(h["ID_FORNECEDOR"]) else "",
            "product_id": pid, "day": day, "cfop": val(r["S_CFOP"]) or "", "class": cls,
            "qty_recorded": r["QUANTIDADE"], "units_per_pack": caixa,
            "qty_base": conv.qty_base if conv and conv.ok else None,
            "unit": p.unit if p else None,
            "price_per_purchase_unit": cost.price_per_purchase_unit,
            "invoice_cost_per_base_unit": cost.invoice_cost_per_base_unit,
            "recorded_cost_per_base_unit": cost.recorded_cost_per_base_unit,
            "cost_status": cost.cost_status,
        }
        if p is None:
            rec["status"] = "missing_product"
        elif not conv.ok:
            rec["status"] = "unconvertible:" + conv.reason
        elif day < ledger_start:
            rec["status"] = "before_ledger_coverage"
        else:
            rec["status"] = "pending_match"
        lines[(pid, day)].append(rec)

    # match documented lines to the ledger's posted stock effect per (product, day)
    stock = []  # stock-history receipts = ledger C effect, with provenance
    for k, q in ledger.items():
        recs = [x for x in lines.get(k, []) if x["status"] == "pending_match"]
        doc_total = sum((x["qty_base"] for x in recs), Decimal(0))
        if recs and doc_total == q:
            prov = "documented"
            for x in recs:
                x["status"] = "posted"
        elif recs:
            prov = "quantity_mismatch"
            for x in recs:
                x["status"] = "posted_quantity_mismatch"
        else:
            prov = "ledger_without_document"
        p = prods.get(k[0])
        stock.append({"product_id": k[0], "day": k[1], "unit": p.unit if p else None, "qty_base": q,
                      "provenance": prov, "movement_keys": [movement_key(inst, i) for i in ledger_ids[k]],
                      "classes": sorted({x["class"] for x in recs})})
    for recs in lines.values():
        for x in recs:
            if x["status"] == "pending_match":
                x["status"] = "no_stock_effect"  # document without posted stock effect: never counted

    all_lines = [x for recs in lines.values() for x in recs]
    # reconcile by month and unit: ledger == documented + mismatch + undocumented (exact)
    rec_mu = defaultdict(lambda: defaultdict(Decimal))
    for s in stock:
        mu = (s["day"][:7], s["unit"])
        rec_mu[mu]["ledger_C"] += s["qty_base"]
        rec_mu[mu][s["provenance"]] += s["qty_base"]
    for x in all_lines:
        if x["status"] == "posted":
            rec_mu[(x["day"][:7], x["unit"])]["documented_lines"] += x["qty_base"]
        if x["status"] == "no_stock_effect":
            rec_mu[(x["day"][:7], x["unit"])]["no_stock_effect_lines"] += x["qty_base"]
    ok_parts = all(v["ledger_C"] == v["documented"] + v["quantity_mismatch"] + v["ledger_without_document"] for v in rec_mu.values())
    ok_docs = all(v["documented"] == v["documented_lines"] for v in rec_mu.values())
    totals = defaultdict(Decimal)
    for v in rec_mu.values():
        for kk, vv in v.items():
            totals[kk] += vv
    by_unit = defaultdict(lambda: defaultdict(Decimal))
    for (m, u), v in rec_mu.items():
        for kk in ("ledger_C", "documented", "quantity_mismatch", "ledger_without_document", "no_stock_effect_lines"):
            by_unit[u][kk] += v[kk]
    res = {
        "extract": str(ex.path),
        "ledger_start": ledger_start,
        "entry_lines": len(all_lines),
        "line_status": dict(Counter(x["status"].split(":")[0] for x in all_lines)),
        "line_classes": dict(classes),
        "stock_receipt_classes": sorted(STOCK_RECEIPT_CLASSES),
        "posted_line_classes": dict(Counter(x["class"] for x in all_lines if x["status"] == "posted")),
        "cost_status": dict(cost_status),
        "stock_history_product_days": dict(Counter(s["provenance"] for s in stock)),
        "reconcile_month_unit": {"month_unit_cells": len(rec_mu), "ledger_equals_parts_all_cells": ok_parts,
                                 "documented_equals_lines_all_cells": ok_docs,
                                 "totals": {k: str(v) for k, v in sorted(totals.items())},
                                 "by_unit": {str(u): {k: str(v) for k, v in d.items()} for u, d in sorted(by_unit.items(), key=str)}},
        "no_stock_effect_docs": len({x["doc_key"] for x in all_lines if x["status"] == "no_stock_effect"}),
    }
    with (out / "receipt_lines.csv").open("w", newline="", encoding="utf-8") as f:
        cols = list(all_lines[0].keys()) + (["status"] if "status" not in all_lines[0] else [])
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(all_lines)
    with (out / "stock_receipts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["product_id", "day", "unit", "qty_base", "provenance", "classes", "movement_keys"])
        for s in sorted(stock, key=lambda s: (s["day"], s["product_id"])):
            w.writerow([s["product_id"], s["day"], s["unit"], s["qty_base"], s["provenance"], ";".join(s["classes"]), ";".join(s["movement_keys"])])
    (out / "summary.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), indent=2, ensure_ascii=False))
