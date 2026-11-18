"""Testes de autenticação, revogação de token no logout e controle de acesso (RBAC)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.security import hash_password


def test_login_me_and_logout_revokes_token(
    client: TestClient, admin_user: User
) -> None:
    login_res = client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "Admin123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_res = client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == admin_user.email

    logout_res = client.post("/api/auth/logout", headers=headers)
    assert logout_res.status_code == 200

    # Token revogado não pode mais acessar rotas protegidas
    after_logout = client.get("/api/auth/me", headers=headers)
    assert after_logout.status_code == 401


def test_inactive_user_cannot_login(client: TestClient, db_session: Session) -> None:
    user = User(
        name="Inativo",
        email="inativo@empresa.local",
        password_hash=hash_password("Senha123!"),
        role="OPERATOR",
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()

    res = client.post(
        "/api/auth/login",
        json={"email": "inativo@empresa.local", "password": "Senha123!"},
    )
    assert res.status_code == 403


def test_operator_rbac_restrictions_and_allowed_flows(
    client: TestClient,
    admin_headers: dict[str, str],
    operator_headers: dict[str, str],
) -> None:
    # Admin cria categoria e produto
    cat_res = client.post(
        "/api/categories",
        headers=admin_headers,
        json={"name": "Escritório"},
    )
    assert cat_res.status_code == 201
    cat_id = cat_res.json()["id"]

    prod_res = client.post(
        "/api/products",
        headers=admin_headers,
        json={
            "name": "Caneta Azul",
            "sku": "CAN-AZ-01",
            "category_id": cat_id,
            "unit": "UN",
            "unit_cost": "2.50",
            "min_stock": "5",
        },
    )
    assert prod_res.status_code == 201
    prod_id = prod_res.json()["id"]

    # Operador bloqueado em rotas administrativas
    assert client.get("/api/users", headers=operator_headers).status_code == 403
    assert (
        client.post(
            "/api/categories",
            headers=operator_headers,
            json={"name": "Não Permitida"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/products",
            headers=operator_headers,
            json={
                "name": "Outro",
                "sku": "OUTRO-01",
                "category_id": cat_id,
                "unit": "UN",
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/movements/adjustment",
            headers=operator_headers,
            json={
                "product_id": prod_id,
                "direction": "POSITIVO",
                "quantity": "1",
                "notes": "Tentativa operador",
            },
        ).status_code
        == 403
    )
    assert (
        client.get("/api/reports/current-stock", headers=operator_headers).status_code
        == 403
    )
    assert (
        client.get("/api/ai/purchase-suggestions", headers=operator_headers).status_code
        == 403
    )

    # Operador pode consultar produtos, painel e registrar entrada e saída
    assert client.get("/api/products", headers=operator_headers).status_code == 200
    assert client.get("/api/dashboard", headers=operator_headers).status_code == 200

    entry_res = client.post(
        "/api/movements/entry",
        headers=operator_headers,
        json={
            "product_id": prod_id,
            "quantity": "5",
            "reason_code": "RECEBIMENTO",
        },
    )
    assert entry_res.status_code == 201
    mv_id = entry_res.json()["id"]

    exit_res = client.post(
        "/api/movements/exit",
        headers=operator_headers,
        json={
            "product_id": prod_id,
            "quantity": "2",
            "reason_code": "VENDA",
        },
    )
    assert exit_res.status_code == 201
    assert float(exit_res.json()["balance_after"]) == 3.0

    # Operador não pode estornar movimentação
    rev_res = client.post(
        f"/api/movements/{mv_id}/reverse",
        headers=operator_headers,
        json={"notes": "Tentativa de estorno pelo operador"},
    )
    assert rev_res.status_code == 403

    # Filtro por responsável lista usuários e filtra movimentações corretamente
    resp_list = client.get("/api/movements/responsibles", headers=operator_headers)
    assert resp_list.status_code == 200
    assert any(u["name"] == "Operador Teste" for u in resp_list.json())
    op_id = next(u["id"] for u in resp_list.json() if u["name"] == "Operador Teste")
    by_user = client.get(f"/api/movements?user_id={op_id}", headers=operator_headers)
    assert by_user.status_code == 200
    assert by_user.json()["total"] == 2
