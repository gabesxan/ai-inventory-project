"""DB-03 · verify identities, joins and warehouse scope on the key-column export.

Usage (from backend/):  PYTHONPATH=. python3 legacy/firebird/db03/db03_verify.py ~/.estoquefacil-legacy-work/fb15/out/db03

Reads the TSVs written by db03_extract.sh (local, outside Git), prints aggregate evidence,
and writes summary.json next to them. It prints no row-level business data except
source IDs and counts.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from legacy.identity import (
    SourceInstance,
    coupon_key,
    movement_key,
    nf_key,
    nf_line_key,
    nf_natural_key,
    outbound_key,
    outbound_line_key,
    product_key,
    supplier_key,
)

VALID_SALE_OP = "V"
EXTRACT_DATE = "2026-11-23"  # date the source copy was received/fingerprinted (DB-01)


def rows(d: Path, tag: str):
    p = d / f"{tag}.tsv"
    with p.open(newline="", encoding="latin-1") as f:
        for r in csv.reader(f, delimiter="\t"):
            yield [c.strip() for c in r]


def num(s: str) -> Decimal:
    return Decimal(s) if s not in ("", None) else Decimal(0)


def opt_int(s: str):
    return int(s) if s not in ("", None) else None


def main(d: Path) -> dict:
    out: dict = {}

    # ---- instance / company -------------------------------------------------
    cf = list(rows(d, "CF"))
    branches_cfg = sorted({int(r[0]) for r in cf})
    out["configuracoes_rows"] = len(cf)
    out["configuracoes_branches"] = branches_cfg
    out["company_cnpj_roots"] = len({r[1] for r in cf if len(r) > 1 and r[1]})
    for tag, name in (("LJ", "lojas_rows"), ("SL", "saldo_produtos_rows"), ("TE", "tipos_entradas_saidas_rows"), ("PE", "pedidos_rows")):
        out[name] = int(next(rows(d, tag))[0])
    assert len(branches_cfg) == 1, "expected one branch per database in CONFIGURACOES"
    inst = SourceInstance(branch=branches_cfg[0])
    out["source_instance"] = inst.tag

    # ---- products / suppliers ----------------------------------------------
    pr = list(rows(d, "PR"))
    out["products"] = {
        "rows": len(pr),
        "distinct_keys": len({product_key(inst, int(r[0])) for r in pr}),
        "distinct_codigo_interno": len({r[2] for r in pr}),
        "distinct_codigo_barras": len({r[3] for r in pr}),
        "id_loja_values": sorted({r[1] or "NULL" for r in pr}),
    }
    fo = list(rows(d, "FO"))
    cnpj = Counter(r[3] for r in fo if len(r) > 3 and r[3])
    out["suppliers"] = {
        "rows": len(fo),
        "distinct_keys": len({supplier_key(inst, int(r[0])) for r in fo}),
        "distinct_i_numero": len({r[1] for r in fo}),
        "missing_cnpj": sum(1 for r in fo if len(r) < 4 or not r[3]),
        "cnpj_shared_by_2plus": sum(1 for v in cnpj.values() if v > 1),
    }
    product_ids = {int(r[0]) for r in pr}
    supplier_ids = {int(r[0]) for r in fo}

    # ---- NF headers: collisions --------------------------------------------
    nf = list(rows(d, "NF"))
    by_num = defaultdict(set)          # NUMERO -> stable keys
    by_num_branch = defaultdict(set)   # NUMERO -> branches
    natural = Counter()
    for r in nf:
        r += [""] * (12 - len(r))
        k = nf_key(inst, int(r[0]))
        by_num[(r[2], r[3])].add(k)
        by_num_branch[(r[2], r[3])].add(r[1] or str(inst.branch))
        natural[nf_natural_key(inst, opt_int(r[1]), r[2], opt_int(r[5]), r[4], r[3], opt_int(r[6]), opt_int(r[7]))] += 1
    colliding = {n: ks for n, ks in by_num.items() if len(ks) > 1}
    chaves = Counter(r[9] for r in nf if len(r) > 9 and len(r[9]) == 44)
    out["nf_headers"] = {
        "rows": len(nf),
        "distinct_stable_keys": len({nf_key(inst, int(r[0])) for r in nf}),
        "branches": sorted({r[1] for r in nf}),
        "by_tipo": dict(Counter(r[2] for r in nf)),
        "numbers_reused_within_type": len(colliding),
        "headers_on_reused_numbers": sum(len(v) for v in colliding.values()),
        "numbers_in_2plus_branches": sum(1 for v in by_num_branch.values() if len(v) > 1),
        "natural_key_duplicates": sum(1 for v in natural.values() if v > 1),
        "rows_with_44_digit_access_key": sum(chaves.values()),
        "access_key_duplicates": sum(1 for v in chaves.values() if v > 1),
        "orphan_supplier_refs": sum(1 for r in nf if r[6] and int(r[6]) not in supplier_ids),
    }
    # Real-data collision example (IDs only): a reused number whose headers stay distinct.
    if colliding:
        (tipo, numero), ks = max(colliding.items(), key=lambda kv: len(kv[1]))
        out["nf_collision_example"] = {"tipo": tipo, "headers": len(ks), "stable_keys_distinct": len(ks) == len(set(ks))}

    # ---- NF header -> lines ------------------------------------------------
    nfi = list(rows(d, "NFI"))
    header_ids = {int(r[0]) for r in nf}
    lines_per = Counter(int(r[1]) for r in nfi)
    qty_per = defaultdict(Decimal)
    for r in nfi:
        qty_per[int(r[1])] += num(r[3])
    joined = [r for r in nfi if int(r[1]) in header_ids]
    out["nf_lines"] = {
        "rows": len(nfi),
        "distinct_stable_keys": len({nf_line_key(inst, int(r[0])) for r in nfi}),
        "orphan_lines": len(nfi) - len(joined),
        "headers_without_lines": len(header_ids - set(lines_per)),
        "joined_rows": len(joined),
        "qty_total": str(sum((num(r[3]) for r in nfi), Decimal(0))),
        "qty_joined": str(sum((num(r[3]) for r in joined), Decimal(0))),
        "lines_per_header_min_max": [min(lines_per.values()), max(lines_per.values())] if lines_per else None,
        "orphan_product_refs": sum(1 for r in nfi if int(r[2]) not in product_ids),
        "qty_above_declared_numeric_6_4": sum(1 for r in nfi if num(r[3]) >= 100),
    }

    # ---- outbound header -> lines ------------------------------------------
    sp = list(rows(d, "SP"))
    isp = list(rows(d, "ISP"))
    sp_ids = {int(r[0]) for r in sp}
    out["outbound"] = {
        "headers": len(sp),
        "lines": len(isp),
        "distinct_header_keys": len({outbound_key(inst, int(r[0])) for r in sp}),
        "distinct_line_keys": len({outbound_line_key(inst, int(r[0])) for r in isp}),
        "orphan_lines": sum(1 for r in isp if not r[1] or int(r[1]) not in sp_ids),
        "headers_without_lines": len(sp_ids - {int(r[1]) for r in isp if r[1]}),
    }

    # ---- movements and warehouse selection ----------------------------------
    es = list(rows(d, "ES"))
    out["movements"] = {
        "rows": len(es),
        "distinct_stable_keys": len({movement_key(inst, int(r[0])) for r in es}),
        "by_op": dict(Counter(r[3] for r in es)),
        "branches": sorted({r[1] for r in es}),
    }
    grain = Counter((r[1], r[2], r[3], r[4], r[5]) for r in es)
    out["movements"]["dup_branch_pdv_op_product_date"] = sum(1 for v in grain.values() if v > 1)
    out["movements"]["pdvs"] = sorted({int(r[2]) for r in es})

    def valid_sale(r):
        return (
            r[3] == VALID_SALE_OP
            and num(r[6]) > 0
            and int(r[4]) in product_ids
            and r[5] <= EXTRACT_DATE
        )

    cov = defaultdict(lambda: {"rows": 0, "days": set(), "products": set(), "first": None, "last": None})
    excluded = Counter()
    for r in es:
        if r[3] != VALID_SALE_OP:
            continue
        if not valid_sale(r):
            excluded["qty<=0" if num(r[6]) <= 0 else "future_or_orphan"] += 1
            continue
        c = cov[int(r[1])]
        c["rows"] += 1
        c["days"].add(r[5])
        c["products"].add(r[4])
        c["first"] = min(c["first"] or r[5], r[5])
        c["last"] = max(c["last"] or r[5], r[5])
    by_year = Counter(r[5][:4] for r in es if r[3] == VALID_SALE_OP)
    ranking = sorted(cov.items(), key=lambda kv: (-len(kv[1]["days"]), -kv[1]["rows"], kv[0]))
    out["warehouse_selection"] = {
        "valid_sale_filter": f"S_OPERACAO='{VALID_SALE_OP}' AND F_QUANTIDADE>0 AND product exists AND D_DATA<={EXTRACT_DATE}",
        "excluded_sale_rows": dict(excluded),
        "candidates": [
            {"branch": b, "valid_sale_rows": c["rows"], "sale_days": len(c["days"]),
             "products_sold": len(c["products"]), "first": c["first"], "last": c["last"]}
            for b, c in ranking
        ],
        "rule": "max sale_days, then max valid_sale_rows, then lowest branch id (stable source key)",
        "selected_branch": ranking[0][0] if ranking else None,
        "sale_rows_by_year": dict(sorted(by_year.items())),
    }

    # ---- coupons ------------------------------------------------------------
    icc = list(rows(d, "ICC"))
    coupons = {coupon_key(inst, opt_int(r[1]), opt_int(r[2]), r[3], r[4]) for r in icc}
    numbers_only = {r[4] for r in icc}
    num_pdv = defaultdict(set)
    for r in icc:
        num_pdv[r[4]].add((r[2], r[3]))
    out["coupon_lines"] = {
        "rows": len(icc),
        "distinct_coupons_branch_pdv_date_number": len(coupons),
        "distinct_numbers_only": len(numbers_only),
        "numbers_reused_across_pdv_or_date": sum(1 for v in num_pdv.values() if len(v) > 1),
        "pdvs": sorted({r[2] for r in icc}),
    }

    (d / "summary.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return out


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1]).expanduser()), indent=2, ensure_ascii=False))
