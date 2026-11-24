"""Read stored suggestions independently of training and inference."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Product
from app.models.replenishment import ReplenishmentRun, ReplenishmentSnapshot, ReplenishmentState
from app.schemas.reports import ComparisonRow, ModelSource, ReplenishmentRow, ReportStatus, VersionedReport


def stored_replenishment(
    db: Session, sku: str | None, warehouse: str | None, page: int, page_size: int
) -> VersionedReport[ReplenishmentRow]:
    query = (
        select(ReplenishmentState, ReplenishmentSnapshot, Product.updated_at)
        .outerjoin(ReplenishmentSnapshot, ReplenishmentState.snapshot_id == ReplenishmentSnapshot.id)
        .outerjoin(Product, Product.sku == ReplenishmentState.sku)
        .order_by(ReplenishmentState.sku, ReplenishmentState.warehouse)
    )
    if sku is not None:
        query = query.where(ReplenishmentState.sku == sku)
    if warehouse is not None:
        query = query.where(ReplenishmentState.warehouse == warehouse)
    rows = db.execute(query).all()
    states = {state.status for state, _, _ in rows}
    now = datetime.now(timezone.utc)
    stored = []
    status: ReportStatus = "empty"
    message = "Nenhuma sugestão no recorte selecionado."
    for state, snapshot, product_updated_at in rows:
        if snapshot is None:
            continue
        stored.append(snapshot.payload)
        if (
            state.status != "ready"
            or snapshot.generated_at < now - timedelta(hours=24)
            or product_updated_at is not None and product_updated_at > snapshot.generated_at
        ):
            status = "stale"
            message = "A sugestão armazenada aguarda atualização."
    if stored and status != "stale":
        status, message = "ready", None
    if not stored:
        if "calculating" in states:
            status, message = "calculating", "Cálculo em andamento."
        elif "insufficient_data" in states:
            status, message = "insufficient_data", "Dados insuficientes para calcular uma sugestão."
        elif "failed" in states:
            status, message = "empty", "O último cálculo falhou. Nenhuma sugestão disponível."
    total = len(stored)
    offset = (page - 1) * page_size
    return VersionedReport[ReplenishmentRow](
        status=status, status_message=message, items=stored[offset:offset + page_size],
        total=total, page=page, page_size=page_size, total_pages=max(1, (total + page_size - 1) // page_size),
    )


def stored_comparison(
    db: Session, source: ModelSource | None, model_run_id: str | None, scenario: str | None,
) -> list[ComparisonRow]:
    query = select(ReplenishmentRun)
    if model_run_id is not None:
        query = query.where(ReplenishmentRun.id == model_run_id)
    if source is not None:
        query = query.where(ReplenishmentRun.source == source)

    rows = []
    for run in db.scalars(query.order_by(ReplenishmentRun.id)):
        metrics = run.evaluation.get("metrics", [])
        if not metrics:
            continue
        generated_at = datetime.fromisoformat(run.evaluation["evaluated_at"])
        reference_date = generated_at.astimezone(ZoneInfo("America/Sao_Paulo")).date()
        for metric in metrics:
            if scenario is None or metric["scenario"] == scenario:
                rows.append(ComparisonRow(
                    model_run_id=run.id, model_version=run.model_version, source=run.source,
                    reference_date=reference_date, trained_at=run.trained_at, generated_at=generated_at,
                    **metric,
                ))
    rows.sort(key=lambda row: (row.model_run_id, row.scenario, row.seed, row.policy))
    return rows
