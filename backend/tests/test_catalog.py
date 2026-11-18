"""Testes de cadastros: SKU duplicado, código de barras opcional único e validação de unidade."""

from fastapi.testclient import TestClient


def test_duplicate_sku_and_optional_unique_barcode(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    cat_res = client.post(
        "/api/categories",
        headers=admin_headers,
        json={"name": "Informática"},
    )
    assert cat_res.status_code == 201
    cat_id = cat_res.json()["id"]

    # Produto 1 sem código de barras (saldo deve começar em zero)
    p1 = client.post(
        "/api/products",
        headers=admin_headers,
        json={
            "name": "Teclado Mecânico",
            "sku": "TEC-001",
            "barcode": "",
            "category_id": cat_id,
            "unit": "UN",
            "unit_cost": "199.90",
            "min_stock": "3",
        },
    )
    assert p1.status_code == 201
    assert float(p1.json()["current_stock"]) == 0.0

    # Produto 2 também sem código de barras deve funcionar normalmente
    p2 = client.post(
        "/api/products",
        headers=admin_headers,
        json={
            "name": "Mouse Pad",
            "sku": "MPD-001",
            "barcode": None,
            "category_id": cat_id,
            "unit": "UN",
            "unit_cost": "25.00",
            "min_stock": "5",
        },
    )
    assert p2.status_code == 201

    # SKU duplicado (mesmo em minúsculas) deve retornar 409
    dup_sku = client.post(
        "/api/products",
        headers=admin_headers,
        json={
            "name": "Outro Teclado",
            "sku": "tec-001",
            "category_id": cat_id,
            "unit": "UN",
        },
    )
    assert dup_sku.status_code == 409

    # Produto 3 com código de barras preenchido
    p3 = client.post(
        "/api/products",
        headers=admin_headers,
        json={
            "name": "Monitor 24",
            "sku": "MON-024",
            "barcode": "7899999000123",
            "category_id": cat_id,
            "unit": "UN",
            "unit_cost": "850.00",
            "min_stock": "2",
        },
    )
    assert p3.status_code == 201

    # Código de barras duplicado deve retornar 409
    dup_bar = client.post(
        "/api/products",
        headers=admin_headers,
        json={
            "name": "Monitor 27",
            "sku": "MON-027",
            "barcode": "7899999000123",
            "category_id": cat_id,
            "unit": "UN",
        },
    )
    assert dup_bar.status_code == 409


def test_unit_precision_and_lock_after_movements(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    cat_res = client.post(
        "/api/categories", headers=admin_headers, json={"name": "Insumos"}
    )
    cat_id = cat_res.json()["id"]

    # Estoque mínimo fracionário em unidade discreta UN deve ser rejeitado
    bad_min = client.post(
        "/api/products",
        headers=admin_headers,
        json={
            "name": "Parafuso",
            "sku": "PAR-01",
            "category_id": cat_id,
            "unit": "UN",
            "min_stock": "1.5",
        },
    )
    assert bad_min.status_code == 422

    # Unidade fracionária KG aceita decimais até 3 casas
    kg_prod = client.post(
        "/api/products",
        headers=admin_headers,
        json={
            "name": "Açúcar Cristal",
            "sku": "ACU-KG",
            "category_id": cat_id,
            "unit": "KG",
            "unit_cost": "4.50",
            "min_stock": "5.250",
        },
    )
    assert kg_prod.status_code == 201
    prod_id = kg_prod.json()["id"]

    # Registra entrada fracionária
    entry = client.post(
        "/api/movements/entry",
        headers=admin_headers,
        json={"product_id": prod_id, "quantity": "10.500", "reason_code": "SALDO_INICIAL"},
    )
    assert entry.status_code == 201

    # Após movimentação, tentar alterar unidade deve ser bloqueado
    change_unit = client.put(
        f"/api/products/{prod_id}",
        headers=admin_headers,
        json={
            "name": "Açúcar Cristal",
            "sku": "ACU-KG",
            "category_id": cat_id,
            "unit": "UN",
            "unit_cost": "4.50",
            "min_stock": "5",
        },
    )
    assert change_unit.status_code == 400
