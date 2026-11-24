"""DB-11 · purchase-order pipeline and lead times on the real extract.

    PYTHONPATH=. python3 legacy/firebird/db11/db11_orders.py <extract_dir> <out_dir>

Reports UNAVAILABLE when the source has no orders or no documented order->receipt key.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from legacy.extract import Extract, val
from legacy.purchase_orders import UNAVAILABLE, pipeline


def main(extract_dir: str, out_dir: str) -> dict:
    ex = Extract(Path(extract_dir))
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    entries = [r for r in ex.rows("NOTAS_FISCAIS") if val(r["S_TIPO"]) == "E"]
    with_po = sum(1 for r in entries if val(r["NUMERO_PEDIDO"]))
    orders = ex.count("PEDIDOS")
    lines = ex.count("ITENS_PEDIDO")
    available = orders > 0 and lines > 0 and with_po > 0
    res = {
        "extract": str(ex.path),
        "PEDIDOS_rows": orders, "ITENS_PEDIDO_rows": lines,
        "entry_NF_with_NUMERO_PEDIDO": with_po, "entry_NF_total": len(entries),
        "pipeline": pipeline(None, ex.scope["as_of"]) if not available else "requires order mapping",
        "observed_lead_times": UNAVAILABLE if not available else "requires order mapping",
        "reason": None if available else "no purchase orders and no documented order->receipt key in the snapshot",
        "not_used_as_lead_time": "NF DATA_EMISSAO -> DATA_SAIDA_ENTRADA (supplier transit time, not order lead time)",
        "declared_lead_time_FORNECEDORES_PRAZO_ENTREGA": "not mapped (declared, not measured)",
    }
    (out / "summary.json").write_text(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), indent=2))
