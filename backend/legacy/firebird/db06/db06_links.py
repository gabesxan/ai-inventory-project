"""DB-06 · import real categories/suppliers/links into a DISPOSABLE PostgreSQL and verify.

    LEGACY_PG_SOCKET=<dir> LEGACY_PG_PORT=<port> PYTHONPATH=. python3 legacy/firebird/db06/db06_links.py <extract_dir> <out_dir>

Creates a throwaway database, applies the v1 Alembic schema, imports the plan twice and
checks categories, the supplier filter and the unresolved links. Drops the database at the end.
Writes summary.json and unresolved_links.csv to <out_dir> (outside Git).
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path

import psycopg

from legacy.catalog_links import build_plan, import_plan
from legacy.extract import Extract

BACKEND = Path(__file__).resolve().parents[3]


def main(extract_dir: str, out_dir: str) -> dict:
    sock, port = os.environ["LEGACY_PG_SOCKET"], os.environ["LEGACY_PG_PORT"]
    ex = Extract(Path(extract_dir))
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    plan = build_plan(ex)
    name = "legacy_db06_" + uuid.uuid4().hex[:8]
    admin = psycopg.connect(host=sock, port=port, user="legacy", dbname="postgres", autocommit=True)
    admin.execute(f'CREATE DATABASE "{name}"')
    res: dict = {"database": name}
    try:
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True, capture_output=True,
                       env={**os.environ, "DATABASE_URL": f"postgresql+psycopg://legacy@/{name}?host={sock}&port={port}"})
        with psycopg.connect(host=sock, port=port, user="legacy", dbname=name) as conn:
            res["import_1"] = import_plan(conn, plan)
            counts = lambda: conn.execute("SELECT (SELECT count(*) FROM categories), (SELECT count(*) FROM suppliers), "
                                          "(SELECT count(*) FROM products), (SELECT count(*) FROM legacy_product_suppliers), "
                                          "(SELECT count(*) FROM legacy_unresolved_links)").fetchone()
            first = counts()
            res["import_2"] = import_plan(conn, plan)
            res["db_counts_after_import_1"] = first
            res["db_counts_after_import_2"] = counts()
            res["rerun_identical"] = first == counts()
            origin = {(e, k): t for e, k, t in conn.execute("SELECT entity, origin_key, target_id FROM legacy_origin")}
            # 1. products retain their linked categories
            db_cat = dict(conn.execute("SELECT id, category_id FROM products").fetchall())
            cat_names = dict(conn.execute("SELECT id, name FROM categories").fetchall())
            bad_cat = sum(1 for k, p in plan.products.items() if p["category"] and
                          db_cat[origin[("product", k)]] != origin[("category", p["category"])])
            bad_name = sum(1 for k, n in plan.categories.items() if cat_names[origin[("category", k)]] != n)
            res["categories_check"] = {"products_checked": sum(1 for p in plan.products.values() if p["category"]),
                                       "category_mismatch": bad_cat, "category_name_mismatch": bad_name}
            # 2. supplier filter resolves valid associations
            expected = defaultdict(set)
            for pk, sk, _ in plan.associations:
                expected[origin[("supplier", sk)]].add(origin[("product", pk)])
            got = defaultdict(set)
            for sid, pid in conn.execute("SELECT supplier_id, product_id FROM legacy_product_suppliers"):
                got[sid].add(pid)
            pref_expected = defaultdict(set)
            for k, p in plan.products.items():
                if p["preferred_supplier"]:
                    pref_expected[origin[("supplier", p["preferred_supplier"])]].add(origin[("product", k)])
            pref_got = defaultdict(set)
            for pid, sid in conn.execute("SELECT id, preferred_supplier_id FROM products WHERE preferred_supplier_id IS NOT NULL"):
                pref_got[sid].add(pid)
            res["supplier_filter_check"] = {
                "suppliers_with_links": len(expected),
                "association_filter_mismatch": sum(1 for s in set(expected) | set(got) if expected[s] != got[s]),
                "preferred_filter_mismatch": sum(1 for s in set(pref_expected) | set(pref_got) if pref_expected[s] != pref_got[s]),
                "products_with_preferred_supplier": sum(len(v) for v in pref_got.values()),
            }
            # 3. ambiguous links remain explicitly unresolved
            amb = [u["product_key"] for u in plan.unresolved if u["kind"] == "preferred_supplier_ambiguous"]
            amb_pref = conn.execute("SELECT count(*) FROM products WHERE id = ANY(%s) AND preferred_supplier_id IS NOT NULL",
                                    ([origin[("product", k)] for k in amb],)).fetchone()[0]
            amb_listed = conn.execute("SELECT count(DISTINCT product_key) FROM legacy_unresolved_links WHERE kind = 'preferred_supplier_ambiguous'").fetchone()[0]
            res["unresolved_check"] = {"ambiguous_products": len(amb), "ambiguous_with_preferred_set": amb_pref,
                                       "ambiguous_listed_in_db": amb_listed,
                                       "by_kind": dict(Counter(u["kind"] for u in plan.unresolved))}
    finally:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()
    with (out / "unresolved_links.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["product_key", "kind", "detail"], lineterminator="\n")
        w.writeheader()
        w.writerows(plan.unresolved)
    (out / "summary.json").write_text(json.dumps(res, indent=2, default=str))
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), indent=2, default=str))
