"""Rota do painel operacional (Dashboard)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardOut
from app.services.dashboard_service import get_dashboard_data


router = APIRouter(prefix="/dashboard", tags=["Painel"])


@router.get("", response_model=DashboardOut)
def get_dashboard(
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    days: int = Query(default=30, ge=1, le=365),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> DashboardOut:
    """Retorna indicadores calculados em tempo real e lista de reposição."""
    return get_dashboard_data(db, days=days, start_date=start_date, end_date=end_date)
