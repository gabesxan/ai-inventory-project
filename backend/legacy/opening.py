"""DB-10 · dated opening-stock snapshot: selection, discrepancy report and idempotent import.

Selection (from a DB-04 extract)
* Only a PHYSICAL count with a source date and warehouse is eligible: a closed
  ``CAD_BALANCO`` (``DATA_ENCERRAMENTO``) with its ``ITENS_BALANCO`` lines.
* Book balances (``PRODUTOS.ESTOQUE_ATUAL``) are never opening stock: they go to the
  discrepancy report (negative ones flagged separately). An empty count table proves nothing,
  so no product gets a zero balance from it.

Import (dedicated database, one transaction)
* One opening entry per eligible SKU, tracked in ``legacy_opening_entries`` (unique per product
  key) under ``legacy_opening_snapshots`` (the snapshot's ACTUAL source date and warehouse).
* Re-importing the same snapshot is a no-op. A different snapshot for a product that already has an
  opening, or any product that already has stock movements, is refused: never a reset.
* Positive balances create one v1 ``stock_movements`` row (ENTRADA / SALDO_INICIAL) whose note
  carries the source date. A counted zero is recorded in the legacy table without a movement
  (v1 requires quantity > 0).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

from legacy.extract import Extract, dec, num, val
from legacy.identity import SourceInstance, location_key, product_key
from legacy.products import normalize_products


@dataclass(frozen=True)
class Balance:
    product_key: str
    sku: str
    qty: Decimal
    unit: str


@dataclass
class Snapshot:
    snapshot_id: str
    source_date: str          # the date the balances were true (count closing date)
    warehouse_key: str
    source: str               # e.g. "CAD_BALANCO 12" or "fixture"
    entries: List[Balance] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"Saldo inicial legado em {self.source_date} ({self.source})"


@dataclass
class Selection:
    snapshot: Optional[Snapshot]
    discrepancies: List[Dict] = field(default_factory=list)
    reason: Optional[str] = None


def snapshot_id(instance: str, source: str, source_date: str) -> str:
    return hashlib.sha256(f"{instance}|{source}|{source_date}".encode()).hexdigest()[:16]


def select_snapshot(ex: Extract) -> Selection:
    inst = SourceInstance(branch=ex.scope["branch"])
    prods = {p.source_id: p for p in normalize_products(inst, ex.rows("PRODUTOS"))}
    counts = [r for r in ex.rows("CAD_BALANCO") if val(r["DATA_ENCERRAMENTO"])]
    disc: List[Dict] = []
    snap: Optional[Snapshot] = None
    reason = None
    if counts:
        latest = max(counts, key=lambda r: (r["DATA_ENCERRAMENTO"], int(r["ID"])))
        src = f"CAD_BALANCO {latest['ID']}"
        snap = Snapshot(snapshot_id(inst.tag, src, latest["DATA_ENCERRAMENTO"]), latest["DATA_ENCERRAMENTO"],
                        location_key(inst, num(latest["ID_LOJA"])), src)
        for it in ex.rows("ITENS_BALANCO"):
            if num(it["ID_BALANCO"]) != int(latest["ID"]):
                continue
            p = prods.get(num(it["ID_PRODUTO"]) or -1)
            q = dec(it["QTD_ATUAL"])
            if p is None or p.quarantined:
                disc.append({"product_id": num(it["ID_PRODUTO"]), "reason": "product_missing_or_quarantined"})
            elif q is None or val(it["CONTADO"]) != "1":
                disc.append({"product_key": p.key, "reason": "not_counted"})
            elif q < 0:
                disc.append({"product_key": p.key, "qty": str(q), "reason": "negative_count"})
            else:
                snap.entries.append(Balance(p.key, p.sku, q, p.unit))
    else:
        reason = "no_physical_count_in_snapshot (CAD_BALANCO/ITENS_BALANCO empty; SALDO_PRODUTOS empty)"
    counted = {b.product_key for b in snap.entries} if snap else set()
    for r in ex.rows("PRODUTOS"):
        p = prods[int(r["ID"])]
        if p.key in counted:
            continue
        q = dec(r["ESTOQUE_ATUAL"])
        why = "book_balance_not_physically_verified"
        if q is not None and q < 0:
            why = "negative_book_balance"
        disc.append({"product_key": p.key, "sku": p.sku, "book_qty": None if q is None else str(q), "reason": why})
    return Selection(snap, disc, reason)


DDL = """
CREATE TABLE IF NOT EXISTS legacy_opening_snapshots (
    snapshot_id   varchar(32) PRIMARY KEY,
    source_date   date NOT NULL,
    warehouse_key varchar(120) NOT NULL,
    source        varchar(120) NOT NULL,
    label         text NOT NULL,
    imported_at   timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS legacy_opening_entries (
    product_key   varchar(120) PRIMARY KEY,
    snapshot_id   varchar(32) NOT NULL REFERENCES legacy_opening_snapshots(snapshot_id),
    product_id    integer NOT NULL REFERENCES products(id),
    qty           numeric(14,3) NOT NULL CHECK (qty >= 0),
    source_date   date NOT NULL,
    movement_id   integer NULL REFERENCES stock_movements(id)
);
"""


def import_snapshot(conn, snap: Snapshot, user_id: int) -> Dict:
    """Idempotent opening import in ONE transaction (psycopg 3 connection). Returns counts."""
    res = {"created": 0, "zero_recorded": 0, "already_imported": 0, "refused": [], "missing_product": 0}
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(DDL)
            cur.execute(
                "INSERT INTO legacy_opening_snapshots (snapshot_id, source_date, warehouse_key, source, label) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (snapshot_id) DO NOTHING",
                (snap.snapshot_id, snap.source_date, snap.warehouse_key, snap.source, snap.label))
            for b in snap.entries:
                cur.execute("SELECT id, current_stock, unit FROM products WHERE sku = %s FOR UPDATE", (b.sku,))
                row = cur.fetchone()
                if row is None:
                    res["missing_product"] += 1
                    continue
                pid, current, unit = row
                cur.execute("SELECT snapshot_id FROM legacy_opening_entries WHERE product_key = %s", (b.product_key,))
                prev = cur.fetchone()
                if prev:
                    if prev[0] == snap.snapshot_id:
                        res["already_imported"] += 1
                    else:
                        res["refused"].append((b.sku, "opening_exists_from_other_snapshot"))
                    continue
                cur.execute("SELECT count(*) FROM stock_movements WHERE product_id = %s", (pid,))
                if cur.fetchone()[0] or current != 0:
                    res["refused"].append((b.sku, "product_already_has_stock_history"))
                    continue
                mid = None
                if b.qty > 0:
                    cur.execute(
                        "INSERT INTO stock_movements (product_id, movement_type, reason_code, is_demand, quantity, "
                        "signed_quantity, unit_snapshot, balance_before, balance_after, user_id, notes, is_synthetic) "
                        "VALUES (%s, 'ENTRADA', 'SALDO_INICIAL', false, %s, %s, %s, 0, %s, %s, %s, false) RETURNING id",
                        (pid, b.qty, b.qty, unit, b.qty, user_id, snap.label))
                    mid = cur.fetchone()[0]
                    cur.execute("UPDATE products SET current_stock = %s WHERE id = %s", (b.qty, pid))
                    res["created"] += 1
                else:
                    res["zero_recorded"] += 1
                cur.execute(
                    "INSERT INTO legacy_opening_entries (product_key, snapshot_id, product_id, qty, source_date, movement_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s)", (b.product_key, snap.snapshot_id, pid, b.qty, snap.source_date, mid))
    return res
