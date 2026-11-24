"""Replenishment baselines and validation-only parameter search."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.ai.simulator import InventoryEnvironment, Observation, replay


@dataclass(frozen=True)
class BaseStock:
    target: int
    max_order: int

    def __call__(self, state: Observation) -> int:
        return min(self.max_order, max(0, self.target - state.inventory_position))


@dataclass(frozen=True)
class ReorderPoint:
    reorder_point: int
    target: int
    max_order: int

    def __call__(self, state: Observation) -> int:
        if state.inventory_position > self.reorder_point:
            return 0
        return min(self.max_order, max(0, self.target - state.inventory_position))


def fit_baselines(
    validation: Sequence[Callable[[], InventoryEnvironment]],
    candidates: Sequence[int],
    max_order: int,
) -> tuple[BaseStock, ReorderPoint]:
    """Search a common grid. Each factory must return a fresh validation episode."""
    levels = sorted(set(candidates))
    if not validation or len(levels) < 2 or levels[0] < 0 or max_order < 1:
        raise ValueError("Provide validation episodes and at least two nonnegative levels")

    def cost(policy: BaseStock | ReorderPoint) -> float:
        return sum(day.cost for build in validation for day in replay(build(), policy))

    base_stock = min((BaseStock(target, max_order) for target in levels), key=cost)
    reorder = min(
        (ReorderPoint(lower, upper, max_order) for lower in levels for upper in levels if lower < upper),
        key=cost,
    )
    return base_stock, reorder
