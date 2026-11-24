from app.ai.scenarios import DEMO_INVENTORY, DEMO_SCENARIOS, demo_episodes
from app.ai.simulator import replay


def test_splits_have_distinct_seed_and_run_ids():
    splits = [demo_episodes(split) for split in ("train", "validation", "test")]
    assert len(set().union(*(set(episode.run_id for episode in split) for split in splits))) == sum(
        len(split) for split in splits
    )
    assert not ({episode.seed for episode in splits[0]} & {episode.seed for episode in splits[2]})


def test_seed_replays_demand_lead_times_and_receipts():
    for scenario in DEMO_SCENARIOS:
        first, second = scenario.realize(30001), scenario.realize(30001)
        assert first == second
        assert len(first.demand) == len(first.lead_times) == scenario.horizon
        assert all(scenario.lead_min <= days <= scenario.lead_max for days in first.lead_times)
        assert list(replay(first.environment(DEMO_INVENTORY), lambda _: 1)) == list(
            replay(second.environment(DEMO_INVENTORY), lambda _: 1)
        )
    assert DEMO_SCENARIOS[0].realize(30001).demand != DEMO_SCENARIOS[1].realize(30001).demand
