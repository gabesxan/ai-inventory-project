"""CPU Deep Q-Network for bounded whole-unit replenishment decisions."""

import argparse
import logging
import math
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
    epsilon_by_step: bool = False,
    epsilon_decay_fraction: float = 0.8, reward_scale: float = 1.0,
) -> tuple[DQN, int]:
    """Learn from training episodes only and return the number of optimizer updates."""
    if not episodes:
        raise ValueError("At least one training episode is required")
    if passes < 1:
        raise ValueError("At least one training pass is required")
    if not 0 < epsilon_decay_fraction <= 1:
        raise ValueError("Epsilon decay fraction must be in (0, 1]")
    if not epsilon_by_step and epsilon_decay_fraction != 0.8:
        raise ValueError("A custom epsilon decay fraction requires per-step decay")
    if not math.isfinite(reward_scale) or reward_scale <= 0:
        raise ValueError("Reward scale must be positive and finite")
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
    if epsilon_by_step:
        exploration_steps = max(1, epsilon_decay_fraction * sum(len(episode.demand) for episode in ordered_episodes))
    updates = 0
    steps = 0
    LOG.info(
        "CPU DQN seed=%s config=%s episodes=%s epsilon_schedule=%s",
        training.seed, asdict(training), len(ordered_episodes), "step" if epsilon_by_step else "episode",
    )
    for index, episode in enumerate(ordered_episodes):
        # The episode schedule retains the original one-pass decay window.
        epsilon = max(0.05, 1 - index / max(1, 0.8 * len(episodes)))
        env = episode.environment(inventory)
        terminal = False
        total_cost = 0.0
        while not terminal:
            state = env.observation
            if epsilon_by_step:
                epsilon = max(0.05, 1 - steps / exploration_steps)
            action = rng.randrange(inventory.max_order + 1) if rng.random() < epsilon else policy(state)
            day = env.step(action)
            terminal = day.terminal
            total_cost += day.cost
            reward = -day.cost if reward_scale == 1 else -day.cost / reward_scale
            memory.append((_features(state, inventory), action, reward,
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
        if index % 25 == 0 or index + 1 == len(ordered_episodes):
            LOG.info("Iteration %s run=%s cost=%.2f updates=%s", index + 1, episode.run_id, total_cost, updates)
    online.eval()
    return policy, updates


def save_checkpoint(
    path: Path, policy: DQN, training: TrainingConfig, episodes: Sequence[Episode], updates: int,
    *, source: str = "synthetic", scenarios: Sequence[Scenario] = DEMO_SCENARIOS,
    calibration: dict | None = None, training_passes: int = 1,
    epsilon_by_step: bool = False, epsilon_decay_fraction: float = 0.8, reward_scale: float = 1.0,
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
    if epsilon_by_step:
        metadata["epsilon_schedule"] = "step"
    if epsilon_decay_fraction != 0.8:
        metadata["epsilon_decay_fraction"] = epsilon_decay_fraction
    if reward_scale != 1.0:
        metadata["reward_scale"] = reward_scale
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


def train_demo(
    path: Path, seed: int = 42, *, passes: int = 1, epsilon_by_step: bool = False,
    epsilon_decay_fraction: float = 0.8, reward_scale: float = 1.0,
) -> tuple[DQN, dict]:
    training = TrainingConfig(seed=seed)
    episodes = demo_episodes("train")
    policy, updates = train_dqn(
        episodes, DEMO_INVENTORY, training, passes=passes, epsilon_by_step=epsilon_by_step,
        epsilon_decay_fraction=epsilon_decay_fraction, reward_scale=reward_scale,
    )
    return policy, save_checkpoint(
        path, policy, training, episodes, updates, training_passes=passes, epsilon_by_step=epsilon_by_step,
        epsilon_decay_fraction=epsilon_decay_fraction, reward_scale=reward_scale,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train a CPU DQN on synthetic inventory scenarios.")
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--passes", type=int, default=1, help="Repeat each synthetic training run this many times")
    parser.add_argument("--epsilon-by-step", action="store_true", help="Decay epsilon at every environment step")
    parser.add_argument(
        "--epsilon-decay-fraction", type=float, default=0.8,
        help="Fraction of total steps for the per-step decay (default: 0.8)",
    )
    parser.add_argument(
        "--reward-scale", type=float, default=1.0,
        help="Divide training rewards by this positive scale",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    train_demo(
        args.checkpoint, args.seed, passes=args.passes, epsilon_by_step=args.epsilon_by_step,
        epsilon_decay_fraction=args.epsilon_decay_fraction, reward_scale=args.reward_scale,
    )
