import torch

from app.ai.dqn import TrainingConfig, _network, bellman_targets, load_checkpoint, save_checkpoint, train_dqn
from app.ai.scenarios import DEMO_INVENTORY, demo_episodes
from app.ai.simulator import Observation


def test_terminal_transitions_do_not_bootstrap():
    rewards = torch.tensor([-5.0, -4.0])
    targets = bellman_targets(rewards, torch.tensor([float("nan"), 10.0]), torch.tensor([True, False]), 0.9)
    torch.testing.assert_close(targets, torch.tensor([-5.0, 5.0]))


def test_training_changes_weights_and_reload_selects_same_action(tmp_path):
    episodes = demo_episodes("train")[:3]
    training = TrainingConfig(batch_size=8, target_sync_steps=3)
    torch.manual_seed(training.seed)
    initial = _network(DEMO_INVENTORY, training).state_dict()

    policy, updates = train_dqn(episodes, DEMO_INVENTORY, training)
    assert updates > 0
    assert any(not torch.equal(value, initial[name]) for name, value in policy.network.state_dict().items())

    path = tmp_path / "inventory.pt"
    save_checkpoint(path, policy, training, episodes, updates)
    restored, metadata = load_checkpoint(path)
    assert metadata["source"] == "synthetic"
    assert metadata["training_runs"] == [episode.run_id for episode in episodes]
    state = Observation(4, (0, 2, 0, 0, 0))
    assert 0 <= restored(state) == policy(state) <= DEMO_INVENTORY.max_order
