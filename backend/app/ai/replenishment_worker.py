"""Publish DQN recommendations from a separate local process."""

import argparse
import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.calibration import CalibrationDay, CalibrationPlan, assess
from app.ai.dqn import MODEL_VERSION, TrainingConfig, load_checkpoint, save_checkpoint, train_demo, train_dqn
from app.ai.evaluation import evaluate, evaluate_episodes
from app.ai.operational_calibration import BUSINESS_ZONE, assess_operational
from app.ai.publication import publish, record_status
from app.ai.scenarios import DEMO_INVENTORY, DEMO_SCENARIOS, TRAIN_SEEDS, Episode, Scenario
from app.ai.simulator import Observation
from app.database import SessionLocal, engine
from app.models.catalog import Product
from app.models.inventory import StockMovement
from app.models.replenishment import ReplenishmentRun, ReplenishmentSnapshot, ReplenishmentState
from app.schemas.reports import ModelSource, ReplenishmentRow


LOG = logging.getLogger(__name__)
LOCK_ID = 605288143401


@dataclass(frozen=True)
class WorkerConfig:
    sku: str
    warehouse: str
    checkpoint_dir: Path
    revision: str
    seed: int = 42
    pipeline: tuple[int, ...] | None = None
    source: ModelSource = "synthetic"
    configured_lead_time: int | None = None

    def __post_init__(self):
        if self.source == "synthetic" and self.pipeline is None:
            object.__setattr__(self, "pipeline", (0,) * DEMO_INVENTORY.max_lead_time)
        if self.pipeline is not None and any(qty < 0 for qty in self.pipeline):
            raise ValueError("Pipeline quantities must be nonnegative")
        if self.source == "synthetic" and (
            self.pipeline is None or len(self.pipeline) != DEMO_INVENTORY.max_lead_time
        ):
            raise ValueError("Provide one nonnegative pipeline quantity per due day")


def _fingerprint(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _read_product(db: Session, sku: str, *, lock: bool = False) -> Product | None:
    query = select(Product).where(Product.sku == sku).execution_options(populate_existing=True)
    return db.scalar(query.with_for_update() if lock else query)


def _eligible(product: Product | None) -> bool:
    return (
        product is not None
        and product.is_active
        and product.unit == "UN"
        and product.current_stock >= 0
        and product.current_stock == product.current_stock.to_integral_value()
    )


def _inputs(product: Product, pipeline: tuple[int, ...], reference_date: date) -> str:
    return _fingerprint({
        "stock": str(product.current_stock),
        "pipeline": pipeline,
        "date": reference_date.isoformat(),
        "name": product.name,
        "unit": product.unit,
    })


def _chronological_episode(
    name: str, days: tuple[CalibrationDay, ...], lead_time: int, scenario: str,
) -> Episode:
    opening_stock = days[0].opening_stock
    return Episode(
        run_id=f"{name}/{days[0].day.isoformat()}", seed=days[0].day.toordinal(),
        scenario=scenario, demand=tuple(day.demand for day in days),
        lead_times=(lead_time,) * len(days),
        initial_stock=DEMO_SCENARIOS[0].initial_stock if opening_stock is None else opening_stock,
    )


def _train_calibrated(
    path: Path, plan: CalibrationPlan, training: TrainingConfig, revision: str, source: ModelSource,
):
    prefix = "operational" if source == "operational_calibrated" else "legacy"
    scenario_name = f"{prefix}_chronological"
    inventory = replace(DEMO_INVENTORY, max_lead_time=plan.lead_time_days)
    scenario = Scenario(
        f"{prefix}_fitted", len(plan.calibration),
        sum(day.demand for day in plan.calibration) / len(plan.calibration),
        plan.lead_time_days, plan.lead_time_days,
    )
    episodes = tuple(scenario.realize(seed) for seed in TRAIN_SEEDS)
    policy, updates = train_dqn(episodes, inventory, training)
    calibration = {
        "calibration_start": plan.calibration[0].day.isoformat(),
        "calibration_end": plan.calibration[-1].day.isoformat(),
        "lead_time_days": plan.lead_time_days,
        "lead_time_source": plan.lead_time_source,
        "availability_basis": plan.availability_basis,
    }
    if source == "operational_calibrated":
        calibration["evaluation_initial_pipeline"] = "empty_simulated"
        calibration["validation_initial_stock"] = plan.validation[0].opening_stock
        calibration["test_initial_stock"] = plan.test[0].opening_stock
    metadata = save_checkpoint(
        path, policy, training, episodes, updates, source=source,
        scenarios=(scenario,), calibration=calibration,
    )
    evaluation = evaluate_episodes(
        policy, metadata, revision,
        [_chronological_episode(f"{prefix}_validation", plan.validation, plan.lead_time_days, scenario_name)],
        [_chronological_episode(f"{prefix}_test", plan.test, plan.lead_time_days, scenario_name)],
    )
    return policy, metadata, evaluation


def _insufficient(db: Session, config: WorkerConfig, reason: str) -> str:
    state = db.get(ReplenishmentState, (config.sku, config.warehouse))
    current = db.get(ReplenishmentSnapshot, state.snapshot_id) if state and state.snapshot_id else None
    if current is None or current.payload.get("source") == config.source:
        state = record_status(db, config.sku, config.warehouse, "insufficient_data", reason)
        if config.source == "operational_calibrated":
            state.snapshot_id = None
        db.commit()
    LOG.info("Calibration/input eligibility scope=%s source=%s reason=%s", config.sku, config.source, reason)
    return "insufficient_data"


def _process(db: Session, config: WorkerConfig) -> str:
    operational = config.source == "operational_calibrated"
    product = _read_product(db, config.sku, lock=operational)
    if not _eligible(product):
        return _insufficient(db, config, "missing_whole_unit_stock")

    reference_date = datetime.now(BUSINESS_ZONE).date()
    source_version = (product.updated_at, reference_date)
    training = TrainingConfig(seed=config.seed)
    model_config = {
        "version": MODEL_VERSION,
        "source": config.source,
        "inventory": asdict(DEMO_INVENTORY),
        "scenarios": [asdict(scenario) for scenario in DEMO_SCENARIOS],
        "training": asdict(training),
        "training_seeds": TRAIN_SEEDS,
    }
    plan = None
    scenario_name = "synthetic_inventory_v1"
    if config.source == "legacy_calibrated":
        plan, reasons = assess(db, config.warehouse, config.sku, config.configured_lead_time)
        if plan is None:
            return _insufficient(db, config, next(iter(reasons)))
        tracked_stock = db.scalar(
            select(StockMovement.id)
            .where(StockMovement.product_id == product.id, StockMovement.is_synthetic.is_(False))
            .limit(1)
        )
        if tracked_stock is None:
            return _insufficient(db, config, "unverified_operational_stock")
        model_config["legacy_history"] = [
            (day.day.isoformat(), day.demand) for day in (*plan.calibration, *plan.validation, *plan.test)
        ]
        scenario_name = "legacy_chronological"
    elif operational:
        plan, reason = assess_operational(db, product, config.warehouse, reference_date, config.configured_lead_time)
        if plan is None:
            return _insufficient(db, config, reason)
        model_config["operational_history"] = [
            (day.day.isoformat(), day.demand, day.opening_stock)
            for day in (*plan.calibration, *plan.validation, *plan.test)
        ]
        scenario_name = "operational_chronological"
    if plan is not None:
        if config.pipeline is None or len(config.pipeline) != plan.lead_time_days:
            return _insufficient(db, config, "pipeline_unavailable")
        model_config["lead_time_days"] = plan.lead_time_days
        model_config["lead_time_source"] = plan.lead_time_source
    model_hash = _fingerprint(model_config)
    run = db.scalar(
        select(ReplenishmentRun)
        .where(
            ReplenishmentRun.sku == config.sku,
            ReplenishmentRun.warehouse == config.warehouse,
            ReplenishmentRun.config_sha256 == model_hash,
        )
        .order_by(ReplenishmentRun.trained_at.desc(), ReplenishmentRun.id)
        .limit(1)
    )
    state = db.get(ReplenishmentState, (config.sku, config.warehouse))
    snapshot = db.get(ReplenishmentSnapshot, state.snapshot_id) if state and state.snapshot_id else None
    input_hash = _inputs(product, config.pipeline, reference_date)
    checkpoint_dir = config.checkpoint_dir.resolve()
    cached_path = Path(run.checkpoint_path) if run else None
    can_reuse = cached_path is not None and cached_path.parent == checkpoint_dir and cached_path.is_file()
    if can_reuse and snapshot and snapshot.run_id == run.id and snapshot.input_sha256 == input_hash:
        if state.status != "ready":
            record_status(db, config.sku, config.warehouse, "ready")
            db.commit()
        return "unchanged"

    record_status(db, config.sku, config.warehouse, "calculating")
    db.commit()
    if can_reuse:
        policy, _ = load_checkpoint(cached_path)
    else:
        run_id = str(uuid4())
        path = checkpoint_dir / f"{run_id}.pt"
        if plan is None:
            policy, metadata = train_demo(path, config.seed)
            evaluation = evaluate(policy, metadata, config.revision)
        else:
            policy, metadata, evaluation = _train_calibrated(path, plan, training, config.revision, config.source)
        run = ReplenishmentRun(
            id=run_id, sku=config.sku, warehouse=config.warehouse,
            source=metadata["source"], model_version=metadata["model_version"],
            config_sha256=model_hash, checkpoint_path=str(path),
            trained_at=datetime.fromisoformat(metadata["trained_at"]),
            configuration=metadata,
            evaluation=evaluation,
        )

    product = _read_product(db, config.sku, lock=operational)
    if not _eligible(product):
        return _insufficient(db, config, "missing_whole_unit_stock")
    reference_date = datetime.now(BUSINESS_ZONE).date()
    if operational and (product.updated_at, reference_date) != source_version:
        if not can_reuse:
            path.unlink(missing_ok=True)
        return _insufficient(db, config, "operational_inputs_changed")
    input_hash = _inputs(product, config.pipeline, reference_date)
    recommendation = policy(Observation(int(product.current_stock), config.pipeline))
    row = ReplenishmentRow(
        sku=product.sku, product_name=product.name, warehouse=config.warehouse,
        recommended_quantity=recommendation, unit=product.unit,
        model_run_id=run.id, model_version=run.model_version, source=run.source,
        scenario=scenario_name, reference_date=reference_date,
        trained_at=run.trained_at, generated_at=datetime.now(timezone.utc),
    )
    publish(db, run, row, input_hash)
    db.commit()
    return "published"


def run_once(
    config: WorkerConfig, db_engine: Engine = engine, sessions: sessionmaker = SessionLocal
) -> str:
    """One polling tick; the separate connection keeps a lock across commits."""
    with db_engine.connect() as connection:
        acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_ID})
        connection.commit()
        if not acquired:
            return "locked"
        try:
            with sessions() as db:
                try:
                    return _process(db, config)
                except Exception:
                    db.rollback()
                    record_status(db, config.sku, config.warehouse, "failed", "worker_failed")
                    db.commit()
                    raise
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_ID})
            connection.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a DQN replenishment worker.")
    parser.add_argument("--sku", required=True, help="Whole-unit SKU")
    parser.add_argument("--warehouse", default="1")
    parser.add_argument("--checkpoints", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--source", choices=("synthetic", "legacy_calibrated", "operational_calibrated"), default="synthetic",
    )
    parser.add_argument("--lead-time-days", type=int, help="Explicit configured delay for eligible calibrated history")
    parser.add_argument("--pipeline", type=int, nargs="+", help="Known or simulated units per due day")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.interval < 1:
        parser.error("--interval must be positive")
    if args.source == "operational_calibrated" and not args.once:
        parser.error("Operational calibration requires --once and a fresh pipeline for each execution")
    pipeline = tuple(args.pipeline) if args.pipeline is not None else None
    config = WorkerConfig(
        args.sku.strip().upper(), args.warehouse.strip(), args.checkpoints, args.revision, args.seed,
        pipeline, args.source, args.lead_time_days,
    )
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            LOG.info("Replenishment worker result: %s", run_once(config))
        except Exception:
            LOG.exception("Replenishment worker iteration failed")
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
