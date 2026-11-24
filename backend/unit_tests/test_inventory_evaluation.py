from collections import Counter
from decimal import Decimal

from app.ai.dqn import TrainingConfig, load_checkpoint, save_checkpoint, train_dqn
from app.ai.evaluation import evaluate
from app.ai.scenarios import DEMO_INVENTORY, demo_episodes


def test_paired_evaluation_is_reproducible_and_keeps_every_policy(tmp_path):
    training = TrainingConfig(batch_size=8)
    episodes = demo_episodes("train")[:3]
    policy, updates = train_dqn(episodes, DEMO_INVENTORY, training)
    path = tmp_path / "evaluation.pt"
    metadata = save_checkpoint(path, policy, training, episodes, updates)
    result = evaluate(policy, metadata, "demo-revision")
    restored_policy, restored_metadata = load_checkpoint(path)
    restored = evaluate(restored_policy, restored_metadata, "demo-revision")

    assert result["metrics"] == restored["metrics"]
    assert result["walkthrough"] == restored["walkthrough"]
    assert len(result["metrics"]) == 54
    assert set(Counter((row["scenario"], row["seed"]) for row in result["metrics"]).values()) == {3}
    replayed = result["walkthrough"]
    assert replayed[0]["lead_times"] == replayed[1]["lead_times"] == replayed[2]["lead_times"]
    demands = [tuple(day["demand"] for day in row["days"]) for row in replayed]
    assert demands[0] == demands[1] == demands[2]
    assert any(
        Decimal(row["total_cost"]) > Decimal(baseline["total_cost"])
        for row, baseline in zip(result["metrics"][::3], result["metrics"][1::3])
    )
