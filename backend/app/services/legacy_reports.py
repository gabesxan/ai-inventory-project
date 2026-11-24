"""Read verified Firebird staging through the report contracts."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.schemas.reports import ExceptionCoverage, ImportedHistoryRow, InventoryExceptionRow, VersionedReport


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


def inventory_exceptions(
    db: Session, scope: LegacyScope, coverage: ExceptionCoverage | None, page: int, page_size: int,
) -> VersionedReport[InventoryExceptionRow]:
    conditions = ["r.coverage <> 'available'"]
    params = {"start_date": scope.start_date, "end_date": scope.end_date}
    for field, value, clause in (
        ("sku", scope.sku, "p.sku = :sku"),
        ("warehouse", scope.warehouse, "r.warehouse_key = :warehouse"),
        ("start_date", scope.start_date, "r.end_date >= :start_date"),
        ("end_date", scope.end_date, "r.start_date <= :end_date"),
        ("coverage", coverage, "r.coverage = :coverage"),
    ):
        if value is not None:
            conditions.append(clause)
            params[field] = value
    where = " AND ".join(conditions)
    ranges = f"""
        SELECT p.sku, r.warehouse_key AS warehouse, r.batch_id, b.source_date,
               r.coverage, r.day_status,
               greatest(r.start_date, CAST(:start_date AS date)) AS first_day,
               least(r.end_date, CAST(:end_date AS date)) AS last_day
        FROM legacy_coverage_ranges r
        JOIN products p ON p.id = r.product_id
        JOIN legacy_import_batches b ON b.batch_id = r.batch_id
        WHERE {where}
    """
    total = db.scalar(text(f"SELECT coalesce(sum(last_day - first_day + 1), 0) FROM ({ranges}) scoped"), params)
    offset = (page - 1) * page_size
    items = []
    if offset < total:
        # Each range contributes at least its last day to the descending
        # ordering, so later ranges cannot contribute to the requested page.
        query = f"""
            WITH candidates AS (
                {ranges}
                ORDER BY last_day DESC, sku, warehouse, first_day
                LIMIT :candidate_limit
            )
            SELECT sku, warehouse, batch_id, source_date, coverage,
                   first_day + days.day_offset AS reference_date,
                   CASE day_status
                       WHEN 'known_stockout' THEN 'Ruptura registrada na fonte.'
                       WHEN 'calendar_gap' THEN 'A fonte não registrou o dia no período importado.'
                       WHEN 'unknown_quantity' THEN 'Quantidade histórica indisponível.'
                       ELSE 'Disponibilidade histórica desconhecida.'
                   END AS reason
            FROM candidates
            CROSS JOIN LATERAL generate_series(0, last_day - first_day) AS days(day_offset)
            ORDER BY reference_date DESC, sku, warehouse
            LIMIT :page_size OFFSET :offset
        """
        rows = db.execute(
            text(query), {**params, "candidate_limit": offset + page_size, "page_size": page_size, "offset": offset},
        )
        items = [InventoryExceptionRow.model_validate(row) for row in rows.mappings()]
    return VersionedReport[InventoryExceptionRow](
        items=items, total=total, page=page, page_size=page_size,
        total_pages=max(1, (total + page_size - 1) // page_size),
        status="ready" if total else "empty", status_message=None,
    )
