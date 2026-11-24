"""DB-08 · returns, reversals and corrections on the real extract.

    PYTHONPATH=. python3 legacy/firebird/db08/db08_returns.py <extract_dir> <db07_out> <out_dir>

Writes corrections.csv (every return/correction with effective date, signed delta, link and
flag) and summary.json to <out_dir> (outside Git).
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from legacy.extract import Extract, dec, num, val
from legacy.identity import SourceInstance, nf_key
from legacy.products import normalize_products, to_base
from legacy.returns import Return, Sale, net_sales


def main(extract_dir: str, db07: str, out_dir: str) -> dict:
    ex = Extract(Path(extract_dir))
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    inst = SourceInstance(branch=ex.scope["branch"])
    prods = {p.source_id: p for p in normalize_products(inst, ex.rows("PRODUTOS"))}
    records = []

    # 1. ticket subset: positive lines = gross, negative lines = reversals linked on the same coupon
    q3 = Decimal("0.001")  # FLOAT (float32) quantities: the D_QUANTIDADE domain has 3 decimals
    by_coupon = defaultdict(list)
    for r in ex.rows("VENDEDORES_VENDAS"):
        q = Decimal(r["F_QUANTIDADE"]).quantize(q3)
        by_coupon[(r["D_DATA"], val(r["S_CUPOM"]), int(r["ID_PRODUTO"]))].append((int(r["ID"]), q))
    sales, rets = [], []
    for (d, cup, pid), lines in by_coupon.items():
        pos = [(i, q) for i, q in lines if q > 0]
        left = {i: q for i, q in pos}
        for i, q in pos:
            sales.append(Sale(f"vv/{i}", pid, d, q))
        for i, q in sorted((x for x in lines if x[1] < 0), key=lambda x: x[0]):
            need = -q
            exact = [j for j, rem in left.items() if rem == need]
            fit = exact or [j for j, rem in sorted(left.items(), key=lambda kv: -kv[1]) if rem >= need]
            orig = None
            if fit:
                orig = fit[0]
                left[orig] -= need
            rets.append(Return(f"vv/{i}", pid, d, need, f"vv/{orig}" if orig else None, "VENDEDORES_VENDAS",
                               None if orig else "unmatched_ticket_credit"))
    res_vv = net_sales(sales, rets)
    all_vv = sum((q for lines in by_coupon.values() for _, q in lines), Decimal(0))
    linked = sum(1 for r in rets if r.original_sale_id)
    for r in rets:
        records.append([r.return_id, r.product_id, r.effective_date, str(r.signed_delta), r.original_sale_id or "", r.source,
                        r.flag or "linked_reversal"])

    # 2. ledger: daily NET totals; negative days are unlinked corrections (from DB-07 events)
    ledger_corr = []
    for r in csv.DictReader((Path(db07).expanduser() / "events.csv").open(encoding="utf-8")):
        if r["event_type"] == "sale_correction":
            q = Decimal(r["qty"])
            ledger_corr.append(Return(r["movement_key"], int(r["product_id"]), r["day"], -q, None,
                                      "ENTRADAS_SAIDAS V", "negative_daily_total"))
    for r in ledger_corr:
        records.append([r.return_id, r.product_id, r.effective_date, str(r.signed_delta), "", r.source, r.flag])

    # 3. customer-return NFs (entry CFOP x201/x202/x411): no reference to the original sale
    hdr = {int(r["ID"]): r for r in ex.rows("NOTAS_FISCAIS")}
    by_key = {val(h["S_NFE_CHAVE_ACESSO"]): int(h["ID"]) for h in hdr.values() if val(h["S_NFE_CHAVE_ACESSO"])}
    nf_lines = defaultdict(list)
    for r in ex.rows("ITENS_NOTA_FISCAL"):
        nf_lines[int(r["ID_NOTA_FISCAL"])].append(r)
    cust = []
    sup_links = Counter()
    for hid, h in hdr.items():
        for l in nf_lines[hid]:
            suffix = (val(l["S_CFOP"]) or "    ")[1:4]
            pid = int(l["ID_PRODUTO"])
            p = prods.get(pid)
            caixa = num(l["I_UNIDADES_CAIXA"])
            conv = to_base(p, dec(l["QUANTIDADE"]), val(l["S_UNIDADE_MEDIDA"]), Decimal(caixa) if caixa is not None else None) if p else None
            if val(h["S_TIPO"]) == "E" and suffix in ("201", "202", "411"):
                rid = f"{nf_key(inst, hid)}/item/{l['ID']}"
                if conv is None or not conv.ok:
                    records.append([rid, pid, val(h["DATA_SAIDA_ENTRADA"]), "", "", "NF customer return", "unconvertible_or_missing_product"])
                    continue
                r = Return(rid, pid, val(h["DATA_SAIDA_ENTRADA"]), conv.qty_base, None, "NF customer return", "unlinked_customer_return")
                cust.append(r)
                records.append([r.return_id, pid, r.effective_date, str(r.signed_delta), "", r.source, r.flag])
            if val(h["S_TIPO"]) == "A" and suffix == "202":
                orig = by_key.get(val(h["S_CHAVE_NFE_DEVOLUCAO"]) or "")
                if orig is None:
                    sup_links["supplier_return_unlinked"] += 1
                elif any(int(o["ID_PRODUTO"]) == pid for o in nf_lines[orig]):
                    sup_links["supplier_return_linked_to_original_line"] += 1
                else:
                    sup_links["supplier_return_original_doc_without_product"] += 1

    res_cust = net_sales([], cust)
    res = {
        "extract": str(ex.path),
        "ticket_subset_VENDEDORES_VENDAS": {
            "gross": str(res_vv.gross), "reversals": str(res_vv.returns), "net": str(res_vv.net),
            "net_equals_sum_of_all_lines": res_vv.net == all_vv,
            "reversal_lines": len(rets), "linked_to_same_coupon_line": linked, "unmatched_credits": len(rets) - linked,
            "flags": dict(Counter(f["flag"] for f in res_vv.flagged)),
        },
        "ledger_V": {"note": "daily net totals; gross and returns are not separable at this level",
                     "negative_daily_totals": len(ledger_corr),
                     "correction_qty": str(sum((r.qty for r in ledger_corr), Decimal(0)))},
        "customer_return_NFs": {"lines": len(cust), "qty_base": str(res_cust.returns),
                                "linked": 0, "flag": "unlinked_customer_return (no original-sale reference in source)"},
        "supplier_returns_type_A_cfop_202": dict(sup_links),
        "corrections_rows": len(records),
    }
    with (out / "corrections.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["return_id", "product_id", "effective_date", "signed_delta", "original_id", "source", "flag"])
        w.writerows(records)
    (out / "summary.json").write_text(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2], sys.argv[3]), indent=2))
