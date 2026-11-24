from app.ai.baselines import BaseStock, ReorderPoint, fit_baselines
from app.ai.simulator import InventoryConfig, InventoryEnvironment, Observation


def test_baselines_see_pipeline_and_obey_the_common_cap():
    stock_up = BaseStock(target=12, max_order=5)
    reorder = ReorderPoint(reorder_point=6, target=12, max_order=5)

    assert stock_up(Observation(5, (2, 1))) == 4
    assert reorder(Observation(5, (2, 1))) == 0
    assert stock_up(Observation(6, (0, 0))) == 5
    assert reorder(Observation(6, (0, 0))) == 5
    assert stock_up(Observation(13, (0, 0))) == 0


def test_parameter_search_uses_only_supplied_replayable_validation_episodes():
    config = InventoryConfig(5, 1, 1, 0, 0, 10)

    def validation():
        return InventoryEnvironment(config, (0, 4), (1, 1))

    base_stock, reorder = fit_baselines([validation], [0, 2, 4, 6], config.max_order)
    assert base_stock == BaseStock(target=4, max_order=5)
    assert reorder == ReorderPoint(reorder_point=0, target=4, max_order=5)
