"""DB-03 · Stable source identities for the legacy Firebird database.

Rules (see docs/data/DB-03-source-identities.md):

* Every legacy table uses a surrogate ``ID`` filled by a per-database generator
  (``GEN_<TABLE>_ID``). IDs are unique only inside one Firebird database, so every
  stable key carries the *source instance* (the database's ``CONFIGURACOES.I_LOJA``)
  besides the table and ID.
* The branch (``ID_LOJA`` / ``I_LOJA`` / ``LOJA``) is part of the business identity of
  documents, movements and coupons. It is never inferred from numbers alone. Rows
  without a branch column inherit the instance branch.
* Fiscal document numbers are not unique, not even inside one branch: different
  suppliers reuse numbers. The natural document key therefore includes the branch,
  document type, model, series, number and counterparty. The stable key stays
  ID-based, so colliding natural keys stay distinct instead of merging.
* There is a single company: ``CONFIGURACOES`` holds one CNPJ root and ``LOJAS`` is
  empty. The company is recorded as an attribute, not as a key component.

Stdlib only (runs on Python 3.9+).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

SOURCE_SYSTEM = "estoquefacil-fb15"


@dataclass(frozen=True)
class SourceInstance:
    """One legacy Firebird database (one generator space)."""

    branch: int  # CONFIGURACOES.I_LOJA of this database
    system: str = SOURCE_SYSTEM

    @property
    def tag(self) -> str:
        return f"{self.system}/{self.branch}"


def _key(inst: SourceInstance, entity: str, source_id: int) -> str:
    if source_id is None:
        raise ValueError(f"{entity}: missing source ID")
    return f"{inst.tag}/{entity}/{int(source_id)}"


def row_branch(inst: SourceInstance, value: Optional[int]) -> int:
    """Branch of a row: its own branch column, else the instance branch."""
    return inst.branch if value is None else int(value)


# --- master data -------------------------------------------------------------

def product_key(inst: SourceInstance, produto_id: int) -> str:
    """PRODUTOS.ID. Products are instance-wide (PRODUTOS.ID_LOJA is NULL in the source)."""
    return _key(inst, "produto", produto_id)


def supplier_key(inst: SourceInstance, fornecedor_id: int) -> str:
    """FORNECEDORES.ID. I_NUMERO is unique too; CNPJ is not (shared or missing)."""
    return _key(inst, "fornecedor", fornecedor_id)


def location_key(inst: SourceInstance, branch: Optional[int]) -> str:
    """Warehouse = branch. LOCALIZACOES is empty, so there is no sub-location level."""
    return f"{inst.tag}/local/{row_branch(inst, branch)}"


# --- documents and lines -----------------------------------------------------

def nf_key(inst: SourceInstance, nota_id: int) -> str:
    """NOTAS_FISCAIS.ID (stable, never merged on number)."""
    return _key(inst, "nf", nota_id)


def nf_line_key(inst: SourceInstance, item_id: int) -> str:
    """ITENS_NOTA_FISCAL.ID; parent is nf_key(inst, ID_NOTA_FISCAL)."""
    return _key(inst, "nf_item", item_id)


def nf_natural_key(
    inst: SourceInstance,
    branch: Optional[int],
    tipo: str,
    modelo: Optional[int],
    serie: Optional[str],
    numero: str,
    fornecedor_id: Optional[int],
    cliente_id: Optional[int],
) -> Tuple:
    """Business identity used for diagnostics and duplicate detection."""
    return (
        inst.tag,
        row_branch(inst, branch),
        (tipo or "").strip(),
        modelo,
        (serie or "").strip(),
        (numero or "").strip(),
        fornecedor_id,
        cliente_id,
    )


def outbound_key(inst: SourceInstance, saida_id: int) -> str:
    """SAIDA_PRODUTOS.ID (internal outbound document)."""
    return _key(inst, "saida", saida_id)


def outbound_line_key(inst: SourceInstance, item_id: int) -> str:
    """ITENS_SAIDA_PRODUTOS.ID; parent is outbound_key(inst, ID_SAIDA_PRODUTOS)."""
    return _key(inst, "saida_item", item_id)


def movement_key(inst: SourceInstance, movimento_id: int) -> str:
    """ENTRADAS_SAIDAS.ID (stock movement row)."""
    return _key(inst, "mov", movimento_id)


def coupon_key(
    inst: SourceInstance, branch: Optional[int], pdv: Optional[int], data: str, cupom: str
) -> str:
    """POS coupon: COO numbers restart per PDV, so branch + PDV + date + number."""
    return f"{inst.tag}/cupom/{row_branch(inst, branch)}/{pdv}/{data}/{(cupom or '').strip()}"
