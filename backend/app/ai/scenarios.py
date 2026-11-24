"""Immutable scenario parameters and disjoint seeds for paired experiments."""

from dataclasses import dataclass
from typing import Literal

import numpy as np

from app.ai.simulator import InventoryConfig, InventoryEnvironment


DEMO_INVENTORY = InventoryConfig(20, 5, 1, 2, 0, 5)
Split = Literal["train", "validation", "test"]
TRAIN_SEEDS = tuple(range(10001, 10061))
VALIDATION_SEEDS = tuple(range(20001, 20007))
TEST_SEEDS = tuple(range(30001, 30007))


@dataclass(frozen=True)
class Scenario:
    name: str
    horizon: int
    demand_mean: float
    lead_min: int
    lead_max: int
    initial_stock: int = 12
    spike_mean: float | None = None
    spike_start: int = 20
    spike_end: int = 35

    def realize(self, seed: int) -> "Episode":
        rng = np.random.Generator(np.random.PCG64(seed))
        means = [self.demand_mean] * self.horizon
        if self.spike_mean is not None:
            for day in range(self.spike_start, min(self.spike_end, self.horizon)):
                means[day] = self.spike_mean
        return Episode(
            run_id=f"{self.name}/{seed}",
            seed=seed,
            scenario=self.name,
            demand=tuple(rng.poisson(means).tolist()),
            lead_times=tuple(rng.integers(self.lead_min, self.lead_max + 1, self.horizon).tolist()),
            initial_stock=self.initial_stock,
        )


@dataclass(frozen=True)
class Episode:
    run_id: str
    seed: int
    scenario: str
    demand: tuple[int, ...]
    lead_times: tuple[int, ...]
    initial_stock: int

    def environment(self, config: InventoryConfig) -> InventoryEnvironment:
        return InventoryEnvironment(config, self.demand, self.lead_times, self.initial_stock)


DEMO_SCENARIOS = (
    Scenario("baseline", 60, 5, 1, 3),
    Scenario("demand_spike", 60, 5, 1, 3, spike_mean=10),
    Scenario("long_lead_time", 60, 5, 3, 5),
)


def demo_episodes(split: Split) -> tuple[Episode, ...]:
    seeds = {"train": TRAIN_SEEDS, "validation": VALIDATION_SEEDS, "test": TEST_SEEDS}[split]
    return tuple(scenario.realize(seed) for seed in seeds for scenario in DEMO_SCENARIOS)
