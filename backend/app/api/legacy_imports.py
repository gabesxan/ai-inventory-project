"""Evidências de importação e qualidade dos dados do banco legado, restritas a administradores (DB-14)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.reports import ImportQualityRow, VersionedReport
from app.services.legacy_import_service import export_batches_csv, list_batches


router = APIRouter(prefix="/ai/imports/legacy", tags=["Dados e Preparação para IA"])


@router.get("/batches", response_model=VersionedReport[ImportQualityRow])
def get_legacy_import_batches(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    warehouse: str | None = Query(default=None),
    batch_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    export: Literal["csv"] | None = Query(default=None),
):
    """Lotes importados do banco legado com contagens, motivos de rejeição e cobertura. Somente leitura."""
    if export == "csv":
        return Response(
            content=export_batches_csv(db, warehouse=warehouse, batch_id=batch_id),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="lotes_importacao_legado.csv"'},
        )
    items, total, total_pages = list_batches(
        db, warehouse=warehouse, batch_id=batch_id, page=page, page_size=page_size
    )
    return VersionedReport[ImportQualityRow](
        status="ready" if total else "empty",
        status_message=None if total else "Nenhum lote de importação no recorte selecionado.",
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
