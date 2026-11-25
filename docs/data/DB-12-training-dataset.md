# DB-12 follow-up · Temporal dataset from the real series, and what it can support

**Status:** the dataset is built and tested. **The real data does not support DQN calibration or any operational recommendation.** Nothing was published and nothing was trained on real data.

**Code:** `backend/legacy/training_dataset.py` (CLI `python -m legacy.training_dataset`), `backend/legacy/tests/test_training_dataset.py` (7 tests, fixtures). Outputs, outside Git: `~/.estoquefacil-legacy-work/fb15/out/ai-dataset/` (`dataset.csv.gz`, `dataset-manifest.json`).

## Rules

- Only `uncensored` days enter (`sale`, `true_zero`). A day with unknown availability or a calendar gap is **excluded and counted**, never imputed as zero stock or zero demand.
- Splits are chronological by calendar date (70/15/15 of the covered calendar), identical for every SKU, so no later period reaches an earlier split. The manifest records `chronological_check`.
- Every row carries `provenance = firebird_real` and its `availability_basis`.
- `calibration_eligible` is true only when every selected series has the `verified_stock_history` basis that the Codex calibration gate requires. The builder never overrides that gate.

## Real result (warehouse `estoquefacil-fb15/1/local/1`, 2024-02-28 → 2026-11-18, 995 days)

| Split | Days | Rows (sale days) | SKUs |
|---|---|---|---|
| train | 2024-02-28 → 2026-01-23 | 425,074 | 3,622 |
| validation | 2026-01-24 → 2026-06-21 | 92,210 | 2,496 |
| test | 2026-06-22 → 2026-11-18 | 92,204 | 2,453 |

609,488 rows kept. Excluded: 4,653,568 `zero_unknown_availability` days and 112 `unknown_quantity` days. There is no `true_zero` day and no known stockout. The only availability basis is `sales_evidence_only`.

**Why this is not a training set for the DQN:** the kept rows are the days on which something was sold (demand > 0). Demand on a day without a sale is unknown (the shelf may have been empty), so the series is conditioned on a sale and has no zero days. A policy calibrated on it would see only the days that went well.

## Eligibility, measured two ways (same result)

- `python -m app.ai.calibration --warehouse estoquefacil-fb15/1/local/1` (Codex, integration `91729da`) against the disposable import: `insufficient_data`, 691 series excluded as non-whole-unit and 6,235 whole-unit series with `no_verified_availability`, 0 eligible. A configured lead time does not change it.
- Codex's own record in IA-07 (`afc95ca`) reports the same two numbers.

## DQN against the baselines (existing evidence, synthetic only)

Nothing new was trained here. The Codex pipeline's frozen evaluation (`codex/.local/dqn-evaluation.json`, code revision `c1d3ac6`, checkpoint `dqn-v1`, source `synthetic`, 2,685 updates, 18 paired held-out runs, no overlap with the 180 training runs):

| Scenario | Base-stock cost | (s,S) cost | DQN cost | Fill rate (DQN vs base-stock) |
|---|---|---|---|---|
| baseline | 569.67 | 566.83 | 798.83 | 0.598 vs 0.925 |
| demand_spike | 783.00 | 779.67 | 1145.50 | 0.487 vs 0.792 |
| long_lead_time | 734.83 | 736.50 | 816.33 | 0.584 vs 0.679 |

Total cost: DQN 16,564 against 12,525 (base-stock) and 12,498 ((s,S)). On this checkpoint the DQN is worse than both tuned baselines in every scenario. It is a demonstration-scale model, so no claim that RL wins is supported. Real-data evaluation is not implemented either: `evaluate()` refuses a non-synthetic source until a chronological test period exists.

Reproduce (Codex worktree, synthetic): `PYTHONPATH=backend .venv/bin/python -m app.ai.evaluation <checkpoint> <output.json> --revision <commit>`.

## LLM fine-tuning

No part of the system uses an LLM. A search of backend code, docs, requirements and compose files for fine-tuning, OpenAI, Anthropic, LoRA, transformers and similar finds no match; the only learned model is the CPU DQN (`requirements-dqn.txt` adds only `torch`). No fine-tuning was done, and none is justified without an approved architecture.

## Blockers (honest status)

1. **Verified full-day availability.** There is no physical count and no daily stock history, so `verified_stock_history` cannot be established. Without it, no SKU can be calibrated.
2. **Lead times.** There are no purchase orders and no order → receipt history. Lead time stays `unavailable`.
3. **Whole units.** 691 series are weighed or measured (KG, L, M); the DQN is bounded to whole units.
4. **Real-data evaluation.** Not implemented upstream, and not meaningful until 1 and 2 are met.

Recommendations stay on the synthetic path, labelled synthetic. Nothing here enables an operational recommendation.

## Reproduce the dataset

```sh
cd backend
PYTHONPATH=. python -m legacy.training_dataset <fb15/out/db12> <dest> [--warehouse KEY]
PYTHONPATH=. pytest -q legacy/tests/test_training_dataset.py
```
