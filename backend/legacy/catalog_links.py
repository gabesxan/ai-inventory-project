"""DB-06 · categories and supplier links from the legacy catalog into v1 relationships.

Mapping (validated on the real extract, see docs/data/DB-06-categories-and-suppliers.md)
* v1 category = source group ``GRUPOS`` (63 unique names; every product's ``GRUPO`` resolves).
  The department (``DEPARTAMENTOS``) is kept as a staged attribute; a department that is missing
  is an unresolved link, never guessed.
* Supplier = ``FORNECEDORES``: display name (``NOME_FANTASIA`` or ``RAZAO_SOCIAL``) and CNPJ only.
  No contact data.
* Product<->supplier associations = ``CODIGO_REF_FORNECEDOR`` pairs plus ``PRODUTOS.ULT_FORNECEDOR``
  (both validated against FORNECEDORES). ``preferred_supplier_id`` is set ONLY when exactly one
  supplier is evidenced; several candidates stay explicitly unresolved.
* Every imported row is reconciled by its stable origin key (``legacy_origin``), so a rerun
  updates instead of duplicating, and a v1 name clash is reported instead of merged.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from legacy.extract import Extract, num, val
from legacy.identity import SourceInstance, product_key, supplier_key
from legacy.products import normalize_products


def category_key(inst: SourceInstance, grupo_id: int) -> str:
    return f"{inst.tag}/grupo/{grupo_id}"


@dataclass
class CatalogPlan:
    categories: Dict[str, str] = field(default_factory=dict)               # origin key -> name
    suppliers: Dict[str, Tuple[str, Optional[str]]] = field(default_factory=dict)  # key -> (name, cnpj)
    products: Dict[str, dict] = field(default_factory=dict)                 # key -> fields
    associations: Set[Tuple[str, str, str]] = field(default_factory=set)    # (product, supplier, source)
    unresolved: List[dict] = field(default_factory=list)


def _cnpj(v: Optional[str]) -> Optional[str]:
    d = re.sub(r"\D", "", v or "")
    return d if len(d) == 14 else None


def build_plan(ex: Extract) -> CatalogPlan:
    inst = SourceInstance(branch=ex.scope["branch"])
    plan = CatalogPlan()
    groups = {int(r["ID"]): val(r["S_DESCRICAO"]) for r in ex.rows("GRUPOS")}
    depts = {int(r["ID"]): (num(r["ID_GRUPO"]), val(r["S_DESCRICAO"])) for r in ex.rows("DEPARTAMENTOS")}
    for gid, name in groups.items():
        plan.categories[category_key(inst, gid)] = name or f"Grupo {gid}"
    sup_ids = set()
    for r in ex.rows("FORNECEDORES"):
        sid = int(r["ID"])
        sup_ids.add(sid)
        name = val(r["NOME_FANTASIA"]) or val(r["RAZAO_SOCIAL"]) or f"Fornecedor {r['I_NUMERO']}"
        plan.suppliers[supplier_key(inst, sid)] = (name[:150], _cnpj(r["CNPJ"]))
    links: Dict[int, Set[Tuple[int, str]]] = defaultdict(set)
    for r in ex.rows("CODIGO_REF_FORNECEDOR"):
        p, f = num(r["ID_PRODUTO"]), num(r["ID_FORNECEDOR"])
        if p is not None and f is not None:
            links[p].add((f, "CODIGO_REF_FORNECEDOR"))
    staged = {p.source_id: p for p in normalize_products(inst, ex.rows("PRODUTOS"))}
    for r in ex.rows("PRODUTOS"):
        pid = int(r["ID"])
        sp = staged[pid]
        if sp.quarantined:
            continue
        ult = num(r["ULT_FORNECEDOR"])
        if ult is not None:
            links[pid].add((ult, "ULT_FORNECEDOR"))
        g, d = num(r["GRUPO"]), num(r["DEPARTAMENTO"])
        cat = category_key(inst, g) if g in groups else None
        if cat is None:
            plan.unresolved.append({"product_key": sp.key, "kind": "category", "detail": f"GRUPO {g} not in GRUPOS"})
        dept = depts.get(d)
        if d is not None and dept is None:
            plan.unresolved.append({"product_key": sp.key, "kind": "department", "detail": f"DEPARTAMENTO {d} not in DEPARTAMENTOS"})
        elif dept and dept[0] != g:
            plan.unresolved.append({"product_key": sp.key, "kind": "department", "detail": f"DEPARTAMENTO {d} belongs to GRUPO {dept[0]}"})
        valid = {f for f, _ in links[pid] if f in sup_ids}
        for f, src in links[pid]:
            if f in sup_ids:
                plan.associations.add((sp.key, supplier_key(inst, f), src))
            else:
                plan.unresolved.append({"product_key": sp.key, "kind": "supplier_missing", "detail": f"{src} {f}"})
        preferred = supplier_key(inst, next(iter(valid))) if len(valid) == 1 else None
        if len(valid) > 1:
            plan.unresolved.append({"product_key": sp.key, "kind": "preferred_supplier_ambiguous",
                                    "detail": ",".join(str(x) for x in sorted(valid))})
        plan.products[sp.key] = {"sku": sp.sku, "name": sp.name[:180], "unit": sp.unit, "barcode": sp.barcode,
                                 "is_active": sp.active, "category": cat, "preferred_supplier": preferred,
                                 "department": None if dept is None else dept[1]}
    return plan




def _upsert(cur, entity: str, key: str, insert_sql: str, insert_args: tuple, update_sql: str, update_args: tuple) -> int:
    cur.execute("SELECT target_id FROM legacy_origin WHERE entity = %s AND origin_key = %s", (entity, key))
    row = cur.fetchone()
    if row:
        cur.execute(update_sql, update_args + (row[0],))
        return row[0]
    cur.execute(insert_sql, insert_args)
    tid = cur.fetchone()[0]
    cur.execute("INSERT INTO legacy_origin (entity, origin_key, target_id) VALUES (%s, %s, %s)", (entity, key, tid))
    return tid


def import_plan(conn, plan: CatalogPlan) -> dict:
    """Idempotent import in ONE transaction; reconciles every row by its origin key."""
    ids: Dict[str, int] = {}
    with conn.transaction(), conn.cursor() as cur:
        for k, name in sorted(plan.categories.items()):
            ids[k] = _upsert(cur, "category", k, "INSERT INTO categories (name) VALUES (%s) RETURNING id", (name,),
                             "UPDATE categories SET name = %s WHERE id = %s", (name,))
        for k, (name, doc) in sorted(plan.suppliers.items()):
            ids[k] = _upsert(cur, "supplier", k, "INSERT INTO suppliers (name, document) VALUES (%s, %s) RETURNING id",
                             (name, doc), "UPDATE suppliers SET name = %s, document = %s WHERE id = %s", (name, doc))
        for k, p in sorted(plan.products.items()):
            if p["category"] is None:
                continue  # v1 requires a category; the product stays in legacy_unresolved_links
            cat, sup = ids[p["category"]], ids.get(p["preferred_supplier"]) if p["preferred_supplier"] else None
            ids[k] = _upsert(cur, "product", k,
                             "INSERT INTO products (name, sku, barcode, category_id, unit, is_active, preferred_supplier_id) "
                             "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                             (p["name"], p["sku"], p["barcode"], cat, p["unit"], p["is_active"], sup),
                             "UPDATE products SET name = %s, barcode = %s, category_id = %s, unit = %s, is_active = %s, "
                             "preferred_supplier_id = %s WHERE id = %s",
                             (p["name"], p["barcode"], cat, p["unit"], p["is_active"], sup))
        for pk, sk, src in sorted(plan.associations):
            if pk in ids and sk in ids:
                cur.execute("INSERT INTO legacy_product_suppliers VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (ids[pk], ids[sk], src))
        for u in plan.unresolved:
            cur.execute("INSERT INTO legacy_unresolved_links VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (u["product_key"], u["kind"], u["detail"]))
    return {"categories": len(plan.categories), "suppliers": len(plan.suppliers),
            "products": sum(1 for p in plan.products.values() if p["category"]), "associations": len(plan.associations),
            "unresolved": len(plan.unresolved)}
