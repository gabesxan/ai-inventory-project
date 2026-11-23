# DB-11 · Purchase-order arrivals and measured lead times

**Status:**
- Acceptance passes on **FIXTURE**.
- On **real data**, the pipeline and observed lead times are **unavailable**: the snapshot holds no purchase orders and no documented order→receipt key. Nothing has been estimated.

**Verified on:** 2026-11-23 · branch `feat/db-firebird` · input: DB-04 extract `run-a`; receipts from DB-09; supplier links from DB-06

## What the source holds

| Item | Real content |
|---|---|
| `PEDIDOS` / `ITENS_PEDIDO` (purchase orders and lines) | **0 / 0 rows** |
| Entry NFs with `NUMERO_PEDIDO` | **0** of 25,512 |
| NF `DATA_EMISSAO` → `DATA_SAIDA_ENTRADA` | differ on 12,568 entries. This is **supplier transit time, not order lead time**, and is not used |
| `FORNECEDORES.PRAZO_ENTREGA` | a declared delivery time, not measured, so it is not mapped |

An empty order table **can't establish observed lead times or a zero pipeline**. The pipeline is reported as `unavailable`, not as 0.

## Logic for a source with orders (`backend/legacy/purchase_orders.py`)

- A receipt reduces an order line's outstanding quantity only through a **documented link** (order line id), and each receipt is applied once.
- Outstanding = ordered − received, never below zero; over-receipts are flagged. Cancellation closes the remainder.
- Outstanding is bucketed by due date relative to the as-of date: `overdue`, `due_0_7`, `due_8_30`, `due_31_plus`, `no_due_date`.
- A lead time is measured only for a verified pair, from the order date to the first linked receipt. A missing order date leaves it `None`.
- `pipeline(None, …)` returns `unavailable` when the source has no orders.

## Acceptance

### 1. A partial receipt reduces the outstanding quantity correctly: PASS (fixture only)

- **FIXTURE:** a 24-unit line receives 10 → outstanding 14.
- A duplicate delivery of the same receipt doesn't count twice, and a receipt without a documented key is ignored.
- A canceled line contributes 0.
- Bucketed as `due_0_7: 14` and `due_31_plus: 12`.
- No real orders exist, so there is no real partial arrival.

### 2. Missing order dates stay null, and an unknown pipeline stays unavailable: PASS (fixture and real data)

- **FIXTURE:** lead times come out as `[5, None]` (the second order has no date).
- **Real:** `db11_orders.py` reports `pipeline: unavailable` and `observed_lead_times: unavailable` with the reason "no purchase orders and no documented order->receipt key in the snapshot". Neither is zero.

## For other workstreams

IA-07 and any replenishment logic must not assume a measured lead time from this source. A supplier lead time needs either purchase-order data from Gabriel or an explicitly declared, labelled assumption, and that choice belongs to the AI track.
