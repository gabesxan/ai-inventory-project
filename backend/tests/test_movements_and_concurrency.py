"""Testes de movimentações, bloqueio de saldo negativo, concorrência real, ajustes e estornos."""

import threading

from fastapi.testclient import TestClient

from app.models.catalog import Category, Product
from app.models.user import User
from app.schemas.inventory import ExitMovementCreate
from app.services.exceptions import DomainError
from app.services.inventory_service import register_exit
from tests.conftest import TestSessionLocal


def _create_product(client: TestClient, headers: dict[str, str], sku: str = "PROD-01", unit: str = "UN") -> int:
    cat_res = client.post(
        "/api/categories",
        headers=headers,
        json={"name": f"Cat-{sku}"},
    )
    cat_id = cat_res.json()["id"]
    prod_res = client.post(
        "/api/products",
        headers=headers,
        json={
            "name": f"Produto {sku}",
            "sku": sku,
            "category_id": cat_id,
            "unit": unit,
            "unit_cost": "10.00",
            "min_stock": "3",
        },
    )
    assert prod_res.status_code == 201
    return prod_res.json()["id"]


def test_core_flow_entry_exit_block_negative_and_inactive(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    prod_id = _create_product(client, admin_headers, sku="CORE-10")

    # Entrada de 10 unidades
    r_in = client.post(
        "/api/movements/entry",
        headers=admin_headers,
        json={"product_id": prod_id, "quantity": "10", "reason_code": "SALDO_INICIAL"},
    )
    assert r_in.status_code == 201
    assert float(r_in.json()["balance_after"]) == 10.0

    # Saída fracionária em unidade discreta UN deve ser bloqueada
    r_frac = client.post(
        "/api/movements/exit",
        headers=admin_headers,
        json={"product_id": prod_id, "quantity": "1.5", "reason_code": "VENDA"},
    )
    assert r_frac.status_code == 422

    # Saída de 3 unidades -> saldo 7
    r_out = client.post(
        "/api/movements/exit",
        headers=admin_headers,
        json={"product_id": prod_id, "quantity": "3", "reason_code": "VENDA"},
    )
    assert r_out.status_code == 201
    assert float(r_out.json()["balance_after"]) == 7.0
    assert r_out.json()["is_demand"] is True

    # Saída de 8 unidades (maior que 7) deve ser bloqueada
    r_over = client.post(
        "/api/movements/exit",
        headers=admin_headers,
        json={"product_id": prod_id, "quantity": "8", "reason_code": "VENDA"},
    )
    assert r_over.status_code == 400

    # Saldo permanece 7
    prod_detail = client.get(f"/api/products/{prod_id}", headers=admin_headers)
    assert float(prod_detail.json()["current_stock"]) == 7.0

    # Inativar produto bloqueia novas movimentações mas preserva histórico
    inact = client.patch(
        f"/api/products/{prod_id}/status",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert inact.status_code == 200

    blocked_mv = client.post(
        "/api/movements/entry",
        headers=admin_headers,
        json={"product_id": prod_id, "quantity": "1", "reason_code": "RECEBIMENTO"},
    )
    assert blocked_mv.status_code == 400

    hist = client.get(f"/api/movements?product_id={prod_id}", headers=admin_headers)
    assert hist.json()["total"] == 2


def test_concurrent_withdrawals_prevent_negative_balance(
    client: TestClient, admin_headers: dict[str, str], admin_user: User
) -> None:
    prod_id = _create_product(client, admin_headers, sku="CONC-01")
    r_in = client.post(
        "/api/movements/entry",
        headers=admin_headers,
        json={"product_id": prod_id, "quantity": "10", "reason_code": "SALDO_INICIAL"},
    )
    assert r_in.status_code == 201

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt_withdrawal() -> None:
        with TestSessionLocal() as thread_db:
            user = thread_db.get(User, admin_user.id)
            assert user is not None
            barrier.wait(timeout=5)
            try:
                register_exit(
                    thread_db,
                    user=user,
                    payload=ExitMovementCreate(
                        product_id=prod_id,
                        quantity="6",
                        reason_code="VENDA",
                        notes="Saída concorrente",
                    ),
                )
                with lock:
                    outcomes.append("OK")
            except DomainError:
                with lock:
                    outcomes.append("BLOCKED")

    t1 = threading.Thread(target=attempt_withdrawal)
    t2 = threading.Thread(target=attempt_withdrawal)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert sorted(outcomes) == ["BLOCKED", "OK"]
    prod_detail = client.get(f"/api/products/{prod_id}", headers=admin_headers)
    assert float(prod_detail.json()["current_stock"]) == 4.0


def test_adjustments_and_reversals_rules(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    prod_id = _create_product(client, admin_headers, sku="REV-01")

    # Entrada de 10
    e1 = client.post(
        "/api/movements/entry",
        headers=admin_headers,
        json={"product_id": prod_id, "quantity": "10", "reason_code": "RECEBIMENTO"},
    )
    entry_id = e1.json()["id"]

    # Saída de 6 -> saldo 4
    s1 = client.post(
        "/api/movements/exit",
        headers=admin_headers,
        json={"product_id": prod_id, "quantity": "6", "reason_code": "VENDA"},
    )
    exit_id = s1.json()["id"]

    # Tentar estornar a entrada de 10 quando o saldo é 4 deve ser bloqueado (4 - 10 < 0)
    rev_entry_fail = client.post(
        f"/api/movements/{entry_id}/reverse",
        headers=admin_headers,
        json={"notes": "Tentativa inválida de estorno"},
    )
    assert rev_entry_fail.status_code == 400

    # Estornar a saída de 6 -> saldo volta para 10
    rev_exit = client.post(
        f"/api/movements/{exit_id}/reverse",
        headers=admin_headers,
        json={"notes": "Erro de digitação na saída"},
    )
    assert rev_exit.status_code == 201
    rev_id = rev_exit.json()["id"]
    assert float(rev_exit.json()["balance_after"]) == 10.0
    assert rev_exit.json()["reference_movement_id"] == exit_id

    # Estornar a mesma movimentação duas vezes deve ser bloqueado (409)
    dup_rev = client.post(
        f"/api/movements/{exit_id}/reverse",
        headers=admin_headers,
        json={"notes": "Tentativa duplicada"},
    )
    assert dup_rev.status_code == 409

    # Estornar um estorno deve ser bloqueado (400)
    rev_of_rev = client.post(
        f"/api/movements/{rev_id}/reverse",
        headers=admin_headers,
        json={"notes": "Estorno de estorno proibido"},
    )
    assert rev_of_rev.status_code == 400

    # Ajuste positivo e negativo
    adj_pos = client.post(
        "/api/movements/adjustment",
        headers=admin_headers,
        json={
            "product_id": prod_id,
            "direction": "POSITIVO",
            "quantity": "2",
            "notes": "Sobras de inventário físico",
        },
    )
    assert adj_pos.status_code == 201
    assert float(adj_pos.json()["balance_after"]) == 12.0
    assert adj_pos.json()["is_demand"] is False

    adj_neg_fail = client.post(
        "/api/movements/adjustment",
        headers=admin_headers,
        json={
            "product_id": prod_id,
            "direction": "NEGATIVO",
            "quantity": "15",
            "notes": "Ajuste maior que o saldo",
        },
    )
    assert adj_neg_fail.status_code == 400
