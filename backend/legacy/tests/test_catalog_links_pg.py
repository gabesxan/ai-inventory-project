"""DB-06 · catalog-links import on a FIXTURE plan against a disposable PostgreSQL."""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from legacy.catalog_links import CatalogPlan, import_plan  # noqa: E402

SOCK, PORT = os.environ.get("LEGACY_PG_SOCKET"), os.environ.get("LEGACY_PG_PORT")
pytestmark = pytest.mark.skipif(not (SOCK and PORT), reason="disposable PostgreSQL not configured")
BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def conn():
    name = "legacy_db06t_" + uuid.uuid4().hex[:8]
    admin = psycopg.connect(host=SOCK, port=PORT, user="legacy", dbname="postgres", autocommit=True)
    admin.execute(f'CREATE DATABASE "{name}"')
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True, capture_output=True,
                   env={**os.environ, "DATABASE_URL": f"postgresql+psycopg://legacy@/{name}?host={SOCK}&port={PORT}"})
    c = psycopg.connect(host=SOCK, port=PORT, user="legacy", dbname=name)
    yield c
    c.close()
    admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    admin.close()


def plan():
    p = CatalogPlan()
    p.categories = {"i/grupo/1": "BEBIDAS", "i/grupo/2": "PADARIA"}
    p.suppliers = {"i/fornecedor/7": ("Distribuidora A", "12345678000190"), "i/fornecedor/8": ("Moinho B", None)}
    p.products = {
        "i/produto/1": {"sku": "000001", "name": "SUCO", "unit": "UN", "barcode": None, "is_active": True,
                        "category": "i/grupo/1", "preferred_supplier": "i/fornecedor/7"},
        "i/produto/2": {"sku": "000002", "name": "PAO", "unit": "KG", "barcode": None, "is_active": True,
                        "category": "i/grupo/2", "preferred_supplier": None},          # two suppliers: ambiguous
    }
    p.associations = {("i/produto/1", "i/fornecedor/7", "CODIGO_REF_FORNECEDOR"),
                      ("i/produto/2", "i/fornecedor/7", "CODIGO_REF_FORNECEDOR"),
                      ("i/produto/2", "i/fornecedor/8", "ULT_FORNECEDOR")}
    p.unresolved = [{"product_key": "i/produto/2", "kind": "preferred_supplier_ambiguous", "detail": "7,8"}]
    return p


def test_categories_supplier_filter_and_unresolved_links_survive_rerun(conn):
    import_plan(conn, plan())
    import_plan(conn, plan())  # rerun: reconciled by origin key, no duplicates
    q = lambda sql, *a: conn.execute(sql, a).fetchall()
    assert q("SELECT p.sku, c.name FROM products p JOIN categories c ON c.id = p.category_id ORDER BY 1") == \
        [("000001", "BEBIDAS"), ("000002", "PADARIA")]
    assert q("SELECT count(*) FROM products")[0][0] == 2 and q("SELECT count(*) FROM suppliers")[0][0] == 2
    by_supplier = q("SELECT s.name, array_agg(p.sku ORDER BY p.sku) FROM legacy_product_suppliers l "
                    "JOIN suppliers s ON s.id = l.supplier_id JOIN products p ON p.id = l.product_id GROUP BY 1 ORDER BY 1")
    assert by_supplier == [("Distribuidora A", ["000001", "000002"]), ("Moinho B", ["000002"])]
    assert q("SELECT sku FROM products WHERE preferred_supplier_id IS NOT NULL") == [("000001",)]
    assert q("SELECT product_key, kind FROM legacy_unresolved_links") == [("i/produto/2", "preferred_supplier_ambiguous")]
