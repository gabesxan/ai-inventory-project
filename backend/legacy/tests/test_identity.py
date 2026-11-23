"""DB-03 acceptance on FIXTURES (synthetic rows shaped like the legacy tables).

The real database holds a single branch (I_LOJA = 1), so cross-branch collisions are
proven here with fixtures. Real-data checks (within-branch number reuse and the NF
header -> line join) live in legacy/firebird/db03/db03_verify.py.
"""
from collections import Counter
from decimal import Decimal

from legacy.identity import (
    SourceInstance,
    coupon_key,
    location_key,
    nf_key,
    nf_line_key,
    nf_natural_key,
    product_key,
)

LOJA1 = SourceInstance(branch=1)
LOJA2 = SourceInstance(branch=2)

# FIXTURE: NOTAS_FISCAIS rows (ID, ID_LOJA, S_TIPO, MODELO, SERIE, NUMERO, ID_FORNECEDOR, ID_CLIENTE)
SAME_DB_TWO_BRANCHES = [
    (10, 1, "E", 55, "1", "000123", 7, None),
    (11, 2, "E", 55, "1", "000123", 7, None),  # same number/series/supplier, other branch
]


def test_same_number_in_two_branches_of_one_database_stays_distinct():
    inst = LOJA1
    keys = {nf_key(inst, r[0]) for r in SAME_DB_TWO_BRANCHES}
    naturals = {nf_natural_key(inst, r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in SAME_DB_TWO_BRANCHES}
    assert len(keys) == 2
    assert len(naturals) == 2  # the branch is part of the natural key


def test_same_id_and_number_in_two_branch_databases_stays_distinct():
    # FIXTURE: two branch databases whose generators both produced NOTAS_FISCAIS.ID = 10.
    a = nf_key(LOJA1, 10)
    b = nf_key(LOJA2, 10)
    assert a != b
    na = nf_natural_key(LOJA1, None, "E", 55, "1", "000123", 7, None)
    nb = nf_natural_key(LOJA2, None, "E", 55, "1", "000123", 7, None)
    assert na != nb  # NULL branch inherits the instance branch
    assert product_key(LOJA1, 5) != product_key(LOJA2, 5)
    assert location_key(LOJA1, None) != location_key(LOJA2, None)


def test_same_number_different_suppliers_same_branch_stays_distinct():
    # Shape of the real case: NF numbers reused by different suppliers inside branch 1.
    rows = [(20, 1, "E", 55, "1", "4511", 3, None), (21, 1, "E", 55, "1", "4511", 9, None)]
    assert len({nf_key(LOJA1, r[0]) for r in rows}) == 2
    assert len({nf_natural_key(LOJA1, *r[1:]) for r in rows}) == 2


def test_header_to_line_join_preserves_counts_and_quantities():
    # FIXTURE: headers and ITENS_NOTA_FISCAL lines (ID, ID_NOTA_FISCAL, QUANTIDADE).
    headers = [10, 11, 12]
    lines = [(100, 10, "2.5000"), (101, 10, "1.0000"), (102, 11, "13020.0000"), (103, 12, "0.0010")]
    header_keys = {nf_key(LOJA1, h): h for h in headers}
    staged = [(nf_line_key(LOJA1, i), nf_key(LOJA1, h), Decimal(q)) for i, h, q in lines]

    joined = [s for s in staged if s[1] in header_keys]
    assert len(joined) == len(lines)
    assert len({s[0] for s in staged}) == len(lines)
    assert Counter(s[1] for s in joined) == Counter(nf_key(LOJA1, h) for _, h, _ in lines)
    assert sum(s[2] for s in joined) == sum(Decimal(q) for *_, q in lines) == Decimal("13023.5010")


def test_coupon_numbers_restart_per_pdv_and_date():
    a = coupon_key(LOJA1, 1, 1, "2026-11-18", "000045")
    b = coupon_key(LOJA1, 1, 2, "2026-11-18", "000045")
    c = coupon_key(LOJA1, 1, 1, "2026-11-17", "000045")
    d = coupon_key(LOJA2, 2, 1, "2026-11-18", "000045")
    assert len({a, b, c, d}) == 4
