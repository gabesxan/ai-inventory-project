import pytest

from app.ai.simulator import InventoryConfig, InventoryEnvironment, Observation


def test_three_day_course_example():
    config = InventoryConfig(20, 2, 1, 2, 0, 5)
    env = InventoryEnvironment(config, (9, 8, 7), (2, 2, 2), 12, (0, 5))

    first = env.step(6)
    assert first.ending_stock == 3
    assert env.observation == Observation(3, (11, 0))
    second = env.step(0)
    assert second.ending_stock == 0
    assert env.observation == Observation(11, (0, 0))
    third = env.step(0)

    days = (first, second, third)
    assert [day.cost for day in days] == [5, 25, 4]
    assert sum(day.cost for day in days) == 34
    assert sum(day.served for day in days) == 19
    assert sum(day.demand for day in days) == 24
    assert [day.ending_stock for day in days] == [3, 0, 4]
    assert third.terminal
    with pytest.raises(ValueError, match="horizon"):
        env.step(0)


def test_last_day_order_is_charged_and_stays_pending():
    config = InventoryConfig(10, 1, 1, 2, 3, 5)
    env = InventoryEnvironment(config, (2,), (1,))
    with pytest.raises(ValueError, match="cap"):
        env.step(11)
    day = env.step(1)
    assert (day.served, day.lost, day.ending_stock) == (0, 2, 0)
    assert day.order_cost == 5
    assert day.shortage_cost == 10
    assert day.next_observation == Observation(0, (1,))
