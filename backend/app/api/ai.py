"""Rotas de preparação de dados históricos para IA e sugestões de compra."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.ai.dataset_builder import (
    export_analytical_movements_csv,
    export_daily_series_csv,
)
from app.ai.import_service import (
    confirm_historical_import,
    generate_historical_template_csv,
    list_import_batches,
    preview_historical_csv,
)
from app.ai.provider import build_purchase_suggestions
from app.api.deps import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.ai import (
    ImportBatchSummaryOut,
    ImportConfirmOut,
    ImportPreviewOut,
    PurchaseSuggestionsResponse,
)


router = APIRouter(prefix="/ai", tags=["Dados e Preparação para IA"])


@router.get("/imports/template")
def download_import_template(
    _admin: Annotated[User, Depends(require_admin)],
) -> Response:
    """Disponibiliza arquivo CSV modelo para importação histórica de estudo."""
    content = generate_historical_template_csv()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="modelo_importacao_historico.csv"'
        },
    )


@router.get("/imports/batches", response_model=list[ImportBatchSummaryOut])
def get_import_batches(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ImportBatchSummaryOut]:
    """Lista os lotes de importação histórica realizados."""
    return list_import_batches(db)


@router.post("/imports/preview", response_model=ImportPreviewOut)
async def post_import_preview(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
) -> ImportPreviewOut:
    """Valida CSV histórico, detecta duplicidades e gera prévia sem gravar nem alterar saldos."""
    content_bytes = await file.read()
    return preview_historical_csv(
        db,
        user=admin,
        filename=file.filename or "historico.csv",
        content_bytes=content_bytes,
    )


@router.post("/imports/{batch_id}/confirm", response_model=ImportConfirmOut)
def post_import_confirm(
    batch_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ImportConfirmOut:
    """Confirma gravação das linhas válidas na base analítica sem alterar o saldo atual."""
    return confirm_historical_import(db, batch_id=batch_id)


@router.get("/exports/daily-series")
def download_daily_series(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    product_id: int | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    include_historical: bool = Query(default=True),
    include_synthetic: bool = Query(default=True),
) -> Response:
    """Exporta visão diária por produto (demanda, ruptura e disponibilidade) para Python/pandas."""
    content = export_daily_series_csv(
        db,
        product_id=product_id,
        start_date=start_date,
        end_date=end_date,
        include_historical=include_historical,
        include_synthetic=include_synthetic,
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="serie_diaria_ia_produtos.csv"'
        },
    )


@router.get("/exports/movements")
def download_analytical_movements(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    include_historical: bool = Query(default=True),
    include_synthetic: bool = Query(default=True),
) -> Response:
    """Exporta movimentações unificadas com identificadores estáveis para análise em Python."""
    content = export_analytical_movements_csv(
        db,
        include_historical=include_historical,
        include_synthetic=include_synthetic,
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="movimentacoes_analiticas_ia.csv"'
        },
    )


@router.get("/purchase-suggestions", response_model=PurchaseSuggestionsResponse)
def get_purchase_suggestions(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    horizon_days: int = Query(default=30, ge=1, le=180),
    simulate: bool = Query(default=False),
) -> PurchaseSuggestionsResponse:
    """Retorna estado do modelo preditivo e sugestões de compra (ou simulação explícita)."""
    return build_purchase_suggestions(db, horizon_days=horizon_days, simulate=simulate)
