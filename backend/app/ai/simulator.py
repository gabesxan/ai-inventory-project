"""Daily lost-sales inventory environment with a positive replenishment delay."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class InventoryConfig:
    max_order: int
    max_lead_time: int
    holding_cost: float
    fixed_order_cost: float
    unit_order_cost: float
    shortage_cost: float

    def __post_init__(self):
        if self.max_order < 1 or self.max_lead_time < 1:
            raise ValueError("Order cap and maximum lead time must be positive")
        costs = (self.holding_cost, self.fixed_order_cost, self.unit_order_cost, self.shortage_cost)
        if any(not math.isfinite(cost) or cost < 0 for cost in costs):
            raise ValueError("Costs must be finite and nonnegative")


@dataclass(frozen=True)
class Observation:
    stock: int
    pipeline: tuple[int, ...]

    @property
    def inventory_position(self) -> int:
        return self.stock + sum(self.pipeline)


@dataclass(frozen=True)
class DayResult:
    order: int
    demand: int
    served: int
    lost: int
    ending_stock: int
    holding_cost: float
    order_cost: float
    shortage_cost: float
    next_observation: Observation
    terminal: bool

    @property
    def cost(self) -> float:
        return self.holding_cost + self.order_cost + self.shortage_cost


class InventoryEnvironment:
    """Receive, decide, reveal demand, then charge costs and advance.

    Initial stock is the on-hand amount at the first decision. Pipeline slots
    correspond to receipts in one through max_lead_time days. At the horizon
    outstanding orders are retained with zero salvage credit or extra penalty.
    """

    def __init__(
        self,
        config: InventoryConfig,
        demand: tuple[int, ...],
        lead_times: tuple[int, ...],
        initial_stock: int = 0,
        initial_pipeline: tuple[int, ...] | None = None,
    ):
        self.config = config
        if not demand or len(demand) != len(lead_times) or any(value < 0 for value in demand):
            raise ValueError("Provide aligned, nonnegative daily demand and lead times")
        if any(not 1 <= value <= config.max_lead_time for value in lead_times):
            raise ValueError("Daily lead times are outside the configured bounds")
        pipeline = (0,) * config.max_lead_time if initial_pipeline is None else initial_pipeline
        if initial_stock < 0 or len(pipeline) != config.max_lead_time or any(qty < 0 for qty in pipeline):
            raise ValueError("Invalid initial stock or receipt pipeline")
        self._demand = tuple(demand)
        self._lead_times = tuple(lead_times)
        self._day = 0
        self.observation = Observation(initial_stock, tuple(pipeline))

    def step(self, order: int) -> DayResult:
        if self._day >= len(self._demand):
            raise ValueError("The simulation has reached its horizon")
        if type(order) is not int or not 0 <= order <= self.config.max_order:
            raise ValueError("Order must be a whole number within the configured cap")
        due = list(self.observation.pipeline)
        due[self._lead_times[self._day] - 1] += order
        demand = self._demand[self._day]
        served = min(self.observation.stock, demand)
        lost = demand - served
        ending_stock = self.observation.stock - served
        self._day += 1
        terminal = self._day == len(self._demand)
        if terminal:
            self.observation = Observation(ending_stock, tuple(due))
        else:
            self.observation = Observation(ending_stock + due[0], tuple(due[1:]) + (0,))
        return DayResult(
            order=order,
            demand=demand,
            served=served,
            lost=lost,
            ending_stock=ending_stock,
            holding_cost=ending_stock * self.config.holding_cost,
            order_cost=order * self.config.unit_order_cost + (self.config.fixed_order_cost if order else 0),
            shortage_cost=lost * self.config.shortage_cost,
            next_observation=self.observation,
            terminal=terminal,
        )
