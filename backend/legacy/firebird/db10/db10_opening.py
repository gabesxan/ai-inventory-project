"""DB-10 · select the opening snapshot on the real extract and write the discrepancy report.

    PYTHONPATH=. python3 legacy/firebird/db10/db10_opening.py <extract_dir> <out_dir>

Writes discrepancies.csv and summary.json to <out_dir> (outside Git). Importing into a
database happens only when a verified physical snapshot exists (legacy.opening.import_snapshot).
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

from legacy.extract import Extract, dec, val
from legacy.opening import select_snapshot


def main(extract_dir: str, out_dir: str) -> dict:
    ex = Extract(Path(extract_dir))
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    sel = select_snapshot(ex)
    last_ledger_day = max(r["D_DATA"] for r in ex.rows("ENTRADAS_SAIDAS") if r["D_DATA"] <= ex.scope["as_of"])
    book = [dec(r["ESTOQUE_ATUAL"]) for r in ex.rows("PRODUTOS")]
    res = {
        "extract": str(ex.path),
        "physical_count_tables": {t: ex.count(t) for t in ("CAD_BALANCO", "ITENS_BALANCO", "SALDO_PRODUTOS")},
        "products_with_ULT_INVENTARIO": sum(1 for r in ex.rows("PRODUTOS") if val(r["ULT_INVENTARIO"])),
        "manual_stock_edits_HIST_ALT_ESTOQUE_MANUAL": ex.count("HIST_ALT_ESTOQUE_MANUAL"),
        "selected_snapshot": None if sel.snapshot is None else {
            "snapshot_id": sel.snapshot.snapshot_id, "source_date": sel.snapshot.source_date,
            "warehouse_key": sel.snapshot.warehouse_key, "eligible_entries": len(sel.snapshot.entries)},
        "no_snapshot_reason": sel.reason,
        "eligible_opening_entries": 0 if sel.snapshot is None else len(sel.snapshot.entries),
        "discrepancy_reasons": dict(Counter(d["reason"] for d in sel.discrepancies)),
        "book_balance_ESTOQUE_ATUAL": {
            "negative": sum(1 for q in book if q is not None and q < 0),
            "zero": sum(1 for q in book if q == 0), "positive": sum(1 for q in book if q is not None and q > 0),
            "sum_positive": str(sum((q for q in book if q is not None and q > 0), Decimal(0))),
            "as_of_note": f"book balance at the snapshot; the source stores no balance date. Latest posted ledger day: {last_ledger_day}; snapshot received {ex.scope['as_of']}",
        },
    }
    with (out / "discrepancies.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["product_key", "sku", "book_qty", "reason", "product_id", "qty"], lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(sel.discrepancies)
    (out / "summary.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), indent=2, ensure_ascii=False))
