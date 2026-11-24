"""Read verified Firebird staging through the report contracts."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.schemas.reports import ImportedHistoryRow, VersionedReport


@dataclass(frozen=True)
class LegacyScope:
    sku: str | None = None
    warehouse: str | None = None
    start_date: date | None = None
    end_date: date | None = None


def _history_scope(scope: LegacyScope, event_type: str | None) -> tuple[str, dict]:
    conditions = []
    params = {}
    for field, value, clause in (
        ("sku", scope.sku, "p.sku = :sku"),
        ("warehouse", scope.warehouse, "h.warehouse_key = :warehouse"),
        ("start_date", scope.start_date, "h.event_date >= :start_date"),
        ("end_date", scope.end_date, "h.event_date <= :end_date"),
        ("event_type", event_type, "h.event_class = :event_type"),
    ):
        if value is not None:
            conditions.append(clause)
            params[field] = value
    sql = "FROM legacy_history_events h JOIN products p ON p.id = h.product_id"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    return sql, params


def _history_rows(sql: str) -> str:
    return f"""
        SELECT h.record_id, p.sku, p.name AS product_name, h.warehouse_key AS warehouse,
               h.event_date, h.event_class AS event_type, h.quantity, h.unit, h.unit_cost,
               h.stock_availability, h.batch_id, h.source_date
        {sql}
        ORDER BY h.event_date DESC, h.record_id, h.warehouse_key
    """


def imported_history(
    db: Session, scope: LegacyScope, event_type: str | None, page: int, page_size: int,
) -> VersionedReport[ImportedHistoryRow]:
    sql, params = _history_scope(scope, event_type)
    total = db.scalar(text(f"SELECT count(*) {sql}"), params)
    items = db.execute(
        text(_history_rows(sql) + " LIMIT :page_size OFFSET :offset"),
        {**params, "page_size": page_size, "offset": (page - 1) * page_size},
    ).mappings()
    return VersionedReport[ImportedHistoryRow](
        items=[ImportedHistoryRow.model_validate(item) for item in items],
        total=total, page=page, page_size=page_size,
        total_pages=max(1, (total + page_size - 1) // page_size),
        status="ready" if total else "empty", status_message=None,
    )


def export_imported_history(
    bind: Engine, scope: LegacyScope, event_type: str | None,
) -> Iterator[ImportedHistoryRow]:
    sql, params = _history_scope(scope, event_type)
    with Session(bind) as db:
        rows = db.execute(text(_history_rows(sql)).execution_options(yield_per=500), params)
        for item in rows.mappings():
            yield ImportedHistoryRow.model_validate(item)
