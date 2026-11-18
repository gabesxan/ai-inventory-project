"""Ponto de entrada da aplicação FastAPI."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    ai,
    auth,
    categories,
    dashboard,
    movements,
    products,
    reports,
    suppliers,
    users,
)
from app.config import settings
from app.services.exceptions import DomainError


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="API de Gestão de Estoque e Preparação de Dados para IA.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    """Converte erros de regra de negócio em respostas JSON padronizadas."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/api/health", tags=["Saúde"])
def healthcheck() -> dict[str, str]:
    """Verifica disponibilidade básica da API."""
    return {"status": "ok"}


app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(users.router, prefix=settings.API_PREFIX)
app.include_router(categories.router, prefix=settings.API_PREFIX)
app.include_router(suppliers.router, prefix=settings.API_PREFIX)
app.include_router(products.router, prefix=settings.API_PREFIX)
app.include_router(movements.router, prefix=settings.API_PREFIX)
app.include_router(dashboard.router, prefix=settings.API_PREFIX)
app.include_router(reports.router, prefix=settings.API_PREFIX)
app.include_router(ai.router, prefix=settings.API_PREFIX)
