"""DB-07 · classify outbound ledger rows on the real extract and publish verified sales totals.

    PYTHONPATH=. python3 legacy/firebird/db07/db07_sales.py <extract_dir> <out_dir>

Writes events.csv (one row per ENTRADAS_SAIDAS outbound row, with event type and linked
documents) and summary.json to <out_dir> (outside Git). Prints aggregates only.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from legacy.extract import Extract, dec, num, val
from legacy.identity import SourceInstance, movement_key, nf_key
from legacy.outbound import Doc, classify, demand_total, summarize
from legacy.products import normalize_products, to_base

OUTBOUND_OPS = {"V", "A", "D", "_", "P"}


def main(extract_dir: str, out_dir: str) -> dict:
    ex = Extract(Path(extract_dir))
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    inst = SourceInstance(branch=ex.scope["branch"])
    prods = {p.source_id: p for p in normalize_products(inst, ex.rows("PRODUTOS"))}

    # outbound fiscal documents (type A): base quantity per (product, day), DB-05 conversion
    hdr = {int(r["ID"]): r for r in ex.rows("NOTAS_FISCAIS")}
    nf_qty = defaultdict(Decimal)
    nf_docs = defaultdict(dict)
    nf_unconv = 0
    for r in ex.rows("ITENS_NOTA_FISCAL"):
        h = hdr[int(r["ID_NOTA_FISCAL"])]
        if val(h["S_TIPO"]) != "A":
            continue
        pid = int(r["ID_PRODUTO"])
        p = prods.get(pid)
        caixa = num(r["I_UNIDADES_CAIXA"])
        c = to_base(p, dec(r["QUANTIDADE"]), val(r["S_UNIDADE_MEDIDA"]), Decimal(caixa) if caixa is not None else None) if p else None
        if c is None or not c.ok:
            nf_unconv += 1
            continue
        k = (pid, val(h["DATA_SAIDA_ENTRADA"]))
        nf_qty[k] += c.qty_base
        nf_docs[k][int(h["ID"])] = Doc(int(h["ID"]), val(h["CFOP"]), val(h["I_NFE_STATUS"]), val(h["B_MOVIMENTACAO_ESTOQUE"]) != "0")

    # internal outbound documents (SAIDA_PRODUTOS type P)
    sp = {int(r["ID"]): r for r in ex.rows("SAIDA_PRODUTOS")}
    sp_qty = defaultdict(Decimal)
    for r in ex.rows("ITENS_SAIDA_PRODUTOS"):
        h = sp.get(num(r["ID_SAIDA_PRODUTOS"]))
        if h and val(h["TIPO_SAIDA"]) == "P":
            sp_qty[(int(r["ID_PRODUTO"]), h["DATA"][:10])] += dec(r["F_QTD"])

    # ledger rows: group per (op, product, day) to match documents, then classify each row
    rows = [r for r in ex.rows("ENTRADAS_SAIDAS") if val(r["S_OPERACAO"]) in OUTBOUND_OPS]
    day_total = defaultdict(Decimal)
    for r in rows:
        day_total[(val(r["S_OPERACAO"]), int(r["ID_PRODUTO"]), r["D_DATA"])] += dec(r["F_QUANTIDADE"])
    events = []
    for r in rows:
        op, pid, day, q = val(r["S_OPERACAO"]), int(r["ID_PRODUTO"]), r["D_DATA"], dec(r["F_QUANTIDADE"])
        k = (pid, day)
        docs = list(nf_docs[k].values()) if op in ("A", "D", "_") and nf_qty.get(k) == day_total[(op, pid, day)] else []
        internal = op == "P" and sp_qty.get(k) == day_total[(op, pid, day)]
        e = classify(int(r["ID"]), pid, day, op, q, docs, internal)
        p = prods.get(pid)
        if e.is_demand and (p is None or p.quarantined):
            e = type(e)(e.movement_id, pid, day, q, "reject", "product_quarantined_or_missing", e.doc_ids)
        if e.is_demand and day > ex.scope["as_of"]:
            e = type(e)(e.movement_id, pid, day, q, "reject", "after_snapshot_date", e.doc_ids)
        events.append((op, e))

    summ = summarize([e for _, e in events])
    by_op = defaultdict(Counter)
    for op, e in events:
        by_op[op][e.event_type] += 1
    demand = [e for _, e in events if e.is_demand]
    monthly = defaultdict(Decimal)
    for e in demand:
        monthly[e.day[:7]] += e.qty
    ledger_v = sum((dec(r["F_QUANTIDADE"]) for r in rows if val(r["S_OPERACAO"]) == "V"), Decimal(0))
    res = {
        "extract": str(ex.path),
        "outbound_ledger_rows": len(rows),
        "events_by_type": {k: {"rows": v["rows"], "qty": str(v["qty"]), "is_demand": v["is_demand"]} for k, v in sorted(summ.items())},
        "events_by_ledger_op": {op: dict(c) for op, c in sorted(by_op.items())},
        "verified_demand_qty": str(demand_total(demand)),
        "verified_demand_rows": len(demand),
        "ledger_V_qty_all_rows": str(ledger_v),
        "demand_days": len({e.day for e in demand}),
        "demand_first_last": [min(e.day for e in demand), max(e.day for e in demand)],
        "demand_by_month_first3_last3": {m: str(q) for m, q in sorted(monthly.items())[:3] + sorted(monthly.items())[-3:]},
        "nf_type_A_lines_unconvertible": nf_unconv,
        "ticket_subset_check": "VENDEDORES_VENDAS product-days are a strict subset of ledger V (DB-07 analysis); not used as demand",
    }
    with (out / "events.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["movement_key", "product_id", "day", "ledger_op", "qty", "event_type", "is_demand", "reason", "doc_keys"])
        for op, e in events:
            w.writerow([movement_key(inst, e.movement_id), e.product_id, e.day, op, e.qty, e.event_type, int(e.is_demand),
                        e.reason or "", ";".join(nf_key(inst, d) for d in e.doc_ids)])
    (out / "summary.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), indent=2, ensure_ascii=False))
