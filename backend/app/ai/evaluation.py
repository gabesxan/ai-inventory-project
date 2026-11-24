"""Paired held-out evaluation with frozen DQN and validation-fit baselines."""

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.ai.baselines import fit_baselines
from app.ai.dqn import DQN, load_checkpoint
from app.ai.scenarios import TEST_SEEDS, VALIDATION_SEEDS, Scenario
from app.ai.simulator import replay


def evaluate(policy: DQN, metadata: dict, revision: str) -> dict:
    scenarios = tuple(Scenario(**config) for config in metadata["scenarios"])
    validation = tuple(scenario.realize(seed) for seed in VALIDATION_SEEDS for scenario in scenarios)
    held_out = tuple(scenario.realize(seed) for seed in TEST_SEEDS for scenario in scenarios)
    training_ids = set(metadata["training_runs"])
    if training_ids.intersection(episode.run_id for episode in (*validation, *held_out)):
        raise ValueError("Evaluation episodes overlap with the checkpoint's training set")
    inventory = policy.inventory
    factories = [lambda episode=episode: episode.environment(inventory) for episode in validation]
    base_stock, reorder = fit_baselines(factories, range(0, 51, 2), inventory.max_order)

    metrics = []
    walkthrough = []
    for episode in held_out:
        for name, choose in (("dqn", policy), ("base_stock", base_stock), ("s_s", reorder)):
            days = list(replay(episode.environment(inventory), choose))
            demand = sum(day.demand for day in days)
            served = sum(day.served for day in days)
            metrics.append({
                "scenario": episode.scenario,
                "seed": episode.seed,
                "policy": name,
                "total_cost": f"{sum(day.cost for day in days):.2f}",
                "fill_rate": f"{served / demand:.8f}" if demand else None,
                "stockout_days": sum(day.lost > 0 for day in days),
                "mean_inventory": f"{sum(day.ending_stock for day in days) / len(days):.8f}",
                "order_days": sum(day.order > 0 for day in days),
            })
            if episode == held_out[0]:
                walkthrough.append({
                    "policy": name,
                    "run_id": episode.run_id,
                    "lead_times": episode.lead_times,
                    "days": [asdict(day) for day in days],
                })
    return {
        "revision": revision,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "checkpoint": metadata,
        "validation_runs": [episode.run_id for episode in validation],
        "test_runs": [episode.run_id for episode in held_out],
        "baselines": {"base_stock": asdict(base_stock), "s_s": asdict(reorder)},
        "metrics": metrics,
        "walkthrough": walkthrough,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate frozen policies on paired held-out simulations.")
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--revision", required=True, help="Local Git commit used to evaluate")
    args = parser.parse_args()
    policy, metadata = load_checkpoint(args.checkpoint)
    result = evaluate(policy, metadata, args.revision)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
