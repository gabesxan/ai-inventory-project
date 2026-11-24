"""Consulta de evidências de qualidade dos lotes importados do banco legado (DB-14).

Somente leitura sobre ``legacy_import_batches``. Não expõe a impressão digital da extração, a
chave de origem das linhas, nem valores do banco legado: apenas contagens e códigos de motivo.
"""

import csv
import io
import json
import math
from datetime import timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.reports import ImportQualityRow

CSV_COLUMNS = [
    "batch_id", "source", "warehouse", "source_date", "period_start", "period_end", "status", "imported_at",
    "accepted_rows", "rejected_rows", "duplicate_rows", "rejection_reasons", "coverage",
]
# Mais recentes primeiro (sem data por último), desempate pelo identificador do lote.
_ORDER = "ORDER BY imported_at DESC NULLS LAST, batch_id ASC"
_SELECT = (
    "SELECT batch_id, warehouse_key AS warehouse, source_date, period_start, period_end, status, imported_at, "
    "accepted_rows, rejected_rows, duplicate_rows, rejection_reasons, coverage FROM legacy_import_batches"
)


def _where(warehouse: str | None, batch_id: str | None) -> tuple[str, dict]:
    clauses, params = [], {}
    if warehouse is not None:
        clauses.append("warehouse_key = :warehouse")
        params["warehouse"] = warehouse
    if batch_id is not None:
        clauses.append("batch_id = :batch_id")
        params["batch_id"] = batch_id
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _row(r) -> ImportQualityRow:
    imported_at = r.imported_at.astimezone(timezone.utc) if r.imported_at else None   # contrato: UTC
    return ImportQualityRow(**{**r._mapping, "imported_at": imported_at, "rejection_reasons": r.rejection_reasons or {}})


def list_batches(
    db: Session, *, warehouse: str | None, batch_id: str | None, page: int, page_size: int
) -> tuple[list[ImportQualityRow], int, int]:
    """Retorna (itens da página, total, total de páginas). Páginas começam em 1; vazio tem uma página."""
    where, params = _where(warehouse, batch_id)
    total = db.execute(text("SELECT count(*) FROM legacy_import_batches" + where), params).scalar_one()
    rows = db.execute(
        text(f"{_SELECT}{where} {_ORDER} LIMIT :limit OFFSET :offset"),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).all()
    return [_row(r) for r in rows], total, max(1, math.ceil(total / page_size))


def export_batches_csv(db: Session, *, warehouse: str | None, batch_id: str | None) -> str:
    """Todo o conjunto filtrado, antes da paginação, na mesma ordem do JSON e com os mesmos valores."""
    where, params = _where(warehouse, batch_id)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for r in db.execute(text(f"{_SELECT}{where} {_ORDER}"), params).all():
        data = _row(r).model_dump(mode="json")
        for nested in ("rejection_reasons", "coverage"):
            data[nested] = "" if data[nested] is None else json.dumps(data[nested], sort_keys=True, separators=(",", ":"))
        writer.writerow(["" if data[c] is None else data[c] for c in CSV_COLUMNS])
    return out.getvalue()
