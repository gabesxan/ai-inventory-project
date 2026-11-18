"""Tipos e validadores compartilhados para schemas Pydantic."""

import re
from typing import Annotated

from pydantic import AfterValidator


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email_format(value: str) -> str:
    """Valida sintaxe básica de e-mail permitindo domínios internos como .local."""
    cleaned = value.strip().lower()
    if not EMAIL_REGEX.match(cleaned) or len(cleaned) > 255:
        raise ValueError("Informe um endereço de e-mail válido.")
    return cleaned


EmailValue = Annotated[str, AfterValidator(validate_email_format)]
