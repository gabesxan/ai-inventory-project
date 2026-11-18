"""Exceções de domínio da camada de regras de negócio."""


class DomainError(Exception):
    """Erro de regra de negócio mapeado para resposta HTTP na camada de API."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
