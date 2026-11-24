"""CPU Deep Q-Network for bounded whole-unit replenishment decisions."""

import argparse
import logging
import random
from collections import deque
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import torch
from torch import nn

from app.ai.scenarios import DEMO_INVENTORY, DEMO_SCENARIOS, Episode, Scenario, demo_episodes
from app.ai.simulator import InventoryConfig, Observation


LOG = logging.getLogger(__name__)
MODEL_VERSION = "dqn-v1"


@dataclass(frozen=True)
class TrainingConfig:
    seed: int = 42
    hidden_size: int = 32
    learning_rate: float = 0.001
    gamma: float = 0.97
    batch_size: int = 64
    replay_capacity: int = 4096
    target_sync_steps: int = 100
    update_every: int = 4


def _features(state: Observation, config: InventoryConfig) -> list[float]:
    return [quantity / config.max_order for quantity in (state.stock, *state.pipeline)]


def _network(inventory: InventoryConfig, training: TrainingConfig) -> nn.Sequential:
    return nn.Sequential(
        nn.Linear(1 + inventory.max_lead_time, training.hidden_size),
        nn.ReLU(),
        nn.Linear(training.hidden_size, training.hidden_size),
        nn.ReLU(),
        nn.Linear(training.hidden_size, inventory.max_order + 1),
    )


@dataclass
class DQN:
    network: nn.Module
    inventory: InventoryConfig

    @torch.inference_mode()
    def __call__(self, observation: Observation) -> int:
        return int(self.network(torch.tensor(_features(observation, self.inventory))).argmax().item())


def bellman_targets(
    rewards: torch.Tensor, next_values: torch.Tensor, terminal: torch.Tensor, gamma: float
) -> torch.Tensor:
    return rewards + gamma * torch.where(terminal, 0.0, next_values)


def train_dqn(
    episodes: Sequence[Episode],
    inventory: InventoryConfig,
    training: TrainingConfig,
    *,
    passes: int = 1,
) -> tuple[DQN, int]:
    """Learn from training episodes only and return the number of optimizer updates."""
    if not episodes:
        raise ValueError("At least one training episode is required")
    if passes < 1:
        raise ValueError("At least one training pass is required")
    torch.set_num_threads(1)
    torch.manual_seed(training.seed)
    rng = random.Random(training.seed)
    online = _network(inventory, training)
    target = _network(inventory, training)
    target.load_state_dict(online.state_dict())
    target.eval()
    policy = DQN(online, inventory)
    optimizer = torch.optim.Adam(online.parameters(), lr=training.learning_rate)
    memory = deque(maxlen=training.replay_capacity)
    ordered_episodes = list(episodes) * passes
    rng.shuffle(ordered_episodes)
    updates = 0
    steps = 0
    LOG.info("CPU DQN seed=%s config=%s episodes=%s", training.seed, asdict(training), len(episodes))
    for index, episode in enumerate(ordered_episodes):
        epsilon = max(0.05, 1 - index / max(1, 0.8 * len(episodes)))
        env = episode.environment(inventory)
        terminal = False
        total_cost = 0.0
        while not terminal:
            state = env.observation
            action = rng.randrange(inventory.max_order + 1) if rng.random() < epsilon else policy(state)
            day = env.step(action)
            terminal = day.terminal
            total_cost += day.cost
            memory.append((_features(state, inventory), action, -day.cost,
                           _features(day.next_observation, inventory), terminal))
            steps += 1
            if steps % training.update_every == 0 and len(memory) >= training.batch_size:
                states, actions, rewards, next_states, terminals = zip(
                    *rng.sample(memory, training.batch_size)
                )
                predicted = online(torch.tensor(states)).gather(
                    1, torch.tensor(actions).unsqueeze(1)
                ).squeeze(1)
                with torch.no_grad():
                    next_values = target(torch.tensor(next_states)).amax(1)
                    expected = bellman_targets(
                        torch.tensor(rewards), next_values, torch.tensor(terminals), training.gamma
                    )
                optimizer.zero_grad()
                nn.functional.smooth_l1_loss(predicted, expected).backward()
                nn.utils.clip_grad_norm_(online.parameters(), 10)
                optimizer.step()
                updates += 1
                if updates % training.target_sync_steps == 0:
                    target.load_state_dict(online.state_dict())
        if index % 25 == 0 or index + 1 == len(episodes):
            LOG.info("Iteration %s run=%s cost=%.2f updates=%s", index + 1, episode.run_id, total_cost, updates)
    online.eval()
    return policy, updates


def save_checkpoint(
    path: Path, policy: DQN, training: TrainingConfig, episodes: Sequence[Episode], updates: int,
    *, source: str = "synthetic", scenarios: Sequence[Scenario] = DEMO_SCENARIOS,
    calibration: dict | None = None, training_passes: int = 1,
) -> dict:
    metadata = {
        "format_version": 1,
        "model_version": MODEL_VERSION,
        "source": source,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "inventory": asdict(policy.inventory),
        "training": asdict(training),
        "scenarios": [asdict(scenario) for scenario in scenarios],
        "training_runs": [episode.run_id for episode in episodes],
        "updates": updates,
        "torch_version": str(torch.__version__),
        "numpy_version": str(np.__version__),
    }
    if training_passes != 1:
        metadata["training_passes"] = training_passes
    if calibration is not None:
        metadata["calibration"] = calibration
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        pending = Path(stream.name)
        try:
            torch.save({"metadata": metadata, "weights": policy.network.state_dict()}, stream)
            stream.flush()
            pending.replace(path)
        finally:
            pending.unlink(missing_ok=True)
    return metadata


def load_checkpoint(path: Path) -> tuple[DQN, dict]:
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    metadata = checkpoint["metadata"]
    if metadata["format_version"] != 1 or metadata["model_version"] != MODEL_VERSION:
        raise ValueError("Unsupported DQN checkpoint version")
    inventory = InventoryConfig(**metadata["inventory"])
    model = _network(inventory, TrainingConfig(**metadata["training"]))
    model.load_state_dict(checkpoint["weights"])
    return DQN(model.eval(), inventory), metadata


def train_demo(path: Path, seed: int = 42, *, passes: int = 1) -> tuple[DQN, dict]:
    training = TrainingConfig(seed=seed)
    episodes = demo_episodes("train")
    policy, updates = train_dqn(episodes, DEMO_INVENTORY, training, passes=passes)
    return policy, save_checkpoint(path, policy, training, episodes, updates, training_passes=passes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train a CPU DQN on synthetic inventory scenarios.")
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--passes", type=int, default=1, help="Repeat each synthetic training run this many times")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    train_demo(args.checkpoint, args.seed, passes=args.passes)
