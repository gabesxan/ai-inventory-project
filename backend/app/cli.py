"""Comandos administrativos via CLI: criação de administrador e dados de demonstração."""

import argparse
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import sys
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.catalog import Category, Product, Supplier
from app.models.inventory import StockMovement, StockoutPeriod
from app.models.user import User
from app.security import hash_password


SAO_PAULO_TZ = ZoneInfo("America/Sao_Paulo")


def cmd_create_admin(name: str, email: str, password: str) -> int:
    """Cria o primeiro administrador (ou um novo administrador) de forma explícita."""
    if len(password) < 6:
        print("Erro: a senha deve ter ao menos 6 caracteres.", file=sys.stderr)
        return 1

    normalized_email = email.strip().lower()
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(func.lower(User.email) == normalized_email))
        if existing:
            print(f"Já existe um usuário com o e-mail {normalized_email}. Nenhuma alteração foi feita.")
            return 0

        admin = User(
            name=name.strip(),
            email=normalized_email,
            password_hash=hash_password(password),
            role="ADMIN",
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print(f"Administrador criado com sucesso: {admin.name} <{admin.email}>")
        return 0


def cmd_seed_demo() -> int:
    """
    Insere dados fictícios de demonstração de forma NÃO destrutiva.
    Nunca apaga registros existentes e ignora itens cujo SKU de demo já exista.
    """
    with SessionLocal() as db:
        actor = db.scalar(
            select(User).where(User.role == "ADMIN", User.is_active.is_(True)).order_by(User.id.asc())
        )
        if not actor:
            print(
                "Erro: crie primeiro um administrador com `python -m app.cli create-admin ...` antes de semear dados de demonstração.",
                file=sys.stderr,
            )
            return 1

        # Cria operador demo opcional se não existir
        op_email = "operador.demo@empresa.local"
        if not db.scalar(select(User).where(func.lower(User.email) == op_email)):
            db.add(
                User(
                    name="Operador Demonstração",
                    email=op_email,
                    password_hash=hash_password("DemoOp123!"),
                    role="OPERATOR",
                    is_active=True,
                )
            )
            db.flush()

        # Categorias demo
        cat_defs = [
            ("Eletrônicos e Periféricos", "Equipamentos de escritório e informática"),
            ("Embalagens e Expedição", "Caixas, fitas adesivas e insumos de envio"),
            ("Insumos de Produção", "Materiais vendidos ou consumidos por peso/volume"),
        ]
        cats: dict[str, Category] = {}
        for cat_name, desc in cat_defs:
            cat = db.scalar(select(Category).where(func.lower(Category.name) == cat_name.lower()))
            if not cat:
                cat = Category(name=cat_name, description=desc, is_active=True)
                db.add(cat)
                db.flush()
            cats[cat_name] = cat

        # Fornecedores demo
        sup_defs = [
            ("Distribuidora Alfa Ltda", "11.222.333/0001-44", "Mariana Silva", "vendas@alfa.local", "(11) 3333-1000", 5),
            ("Embalagens Brasil S.A.", "22.333.444/0001-55", "Carlos Souza", "pedidos@embalagens.local", "(11) 3333-2000", 7),
            ("Química & Insumos Sul", "33.444.555/0001-66", "Renata Lima", "contato@insumosul.local", "(41) 3222-3000", 10),
        ]
        sups: dict[str, Supplier] = {}
        for name, doc, contact, email, phone, lt in sup_defs:
            sup = db.scalar(select(Supplier).where(Supplier.document == doc))
            if not sup:
                sup = Supplier(
                    name=name,
                    document=doc,
                    contact_name=contact,
                    email=email,
                    phone=phone,
                    default_lead_time_days=lt,
                    is_active=True,
                )
                db.add(sup)
                db.flush()
            sups[name] = sup

        now_local = datetime.now(SAO_PAULO_TZ)
        demo_products = [
            {
                "sku": "DEMO-MOUSE-01",
                "barcode": "7891000000011",
                "name": "Mouse Óptico USB Corporativo",
                "category": "Eletrônicos e Periféricos",
                "supplier": "Distribuidora Alfa Ltda",
                "unit": "UN",
                "unit_cost": Decimal("38.50"),
                "min_stock": Decimal("15.000"),
                "safety_stock": Decimal("5.000"),
                "location": "Corredor A - Prateleira 2",
                "lead_time": 5,
                "events": [
                    (-20, "ENTRADA", "SALDO_INICIAL", Decimal("30.000"), Decimal("36.00"), -25, -20, "Saldo inicial de demonstração"),
                    (-15, "SAIDA", "VENDA", Decimal("6.000"), None, None, None, "Saída comercial"),
                    (-10, "SAIDA", "VENDA", Decimal("8.000"), None, None, None, "Saída comercial"),
                    (-6, "SAIDA", "PERDA", Decimal("1.000"), None, None, None, "Unidade com defeito de fábrica"),
                    (-3, "SAIDA", "VENDA", Decimal("7.000"), None, None, None, "Saída comercial"),
                ],
            },
            {
                "sku": "DEMO-CAIXA-02",
                "barcode": "7891000000028",
                "name": "Caixa Papelão Média 30x20x15",
                "category": "Embalagens e Expedição",
                "supplier": "Embalagens Brasil S.A.",
                "unit": "CX",
                "unit_cost": Decimal("24.90"),
                "min_stock": Decimal("20.000"),
                "safety_stock": Decimal("8.000"),
                "location": "Corredor B - Bloco 1",
                "lead_time": 7,
                "events": [
                    (-18, "ENTRADA", "RECEBIMENTO", Decimal("25.000"), Decimal("24.90"), -25, -18, "Recebimento de lote"),
                    (-12, "SAIDA", "CONSUMO", Decimal("10.000"), None, None, None, "Consumo expedição"),
                    (-8, "SAIDA", "CONSUMO", Decimal("15.000"), None, None, None, "Consumo expedição (zerou estoque)"),
                    (-2, "ENTRADA", "RECEBIMENTO", Decimal("30.000"), Decimal("25.20"), -9, -2, "Reposição de estoque"),
                    (-1, "SAIDA", "CONSUMO", Decimal("4.000"), None, None, None, "Consumo diário"),
                ],
            },
            {
                "sku": "DEMO-CAFE-03",
                "barcode": "7891000000035",
                "name": "Café Torrado Especial Grãos",
                "category": "Insumos de Produção",
                "supplier": "Química & Insumos Sul",
                "unit": "KG",
                "unit_cost": Decimal("52.00"),
                "min_stock": Decimal("10.000"),
                "safety_stock": Decimal("3.000"),
                "location": "Corredor C - Secos 1",
                "lead_time": 10,
                "events": [
                    (-14, "ENTRADA", "SALDO_INICIAL", Decimal("18.500"), Decimal("50.00"), -24, -14, "Lote inicial grãos"),
                    (-9, "SAIDA", "VENDA", Decimal("6.250"), None, None, None, "Venda granel"),
                    (-4, "SAIDA", "CONSUMO", Decimal("4.750"), None, None, None, "Consumo copa/degustação"),
                    (-1, "SAIDA", "VENDA", Decimal("2.500"), None, None, None, "Venda varejo"),
                ],
            },
            {
                "sku": "DEMO-FITA-04",
                "barcode": None,
                "name": "Fita Adesiva Larga 48mm",
                "category": "Embalagens e Expedição",
                "supplier": "Embalagens Brasil S.A.",
                "unit": "RL",
                "unit_cost": Decimal("6.80"),
                "min_stock": Decimal("12.000"),
                "safety_stock": Decimal("4.000"),
                "location": "Corredor B - Gaveta 4",
                "lead_time": 7,
                "events": [
                    (-10, "ENTRADA", "RECEBIMENTO", Decimal("10.000"), Decimal("6.80"), -16, -10, "Compra teste"),
                    (-5, "SAIDA", "CONSUMO", Decimal("10.000"), None, None, None, "Esgotado na expedição"),
                ],
            },
        ]

        created_count = 0
        for item in demo_products:
            if db.scalar(select(Product.id).where(Product.sku == item["sku"])):
                continue

            cat = cats[item["category"]]
            sup = sups[item["supplier"]]
            prod = Product(
                name=item["name"],
                sku=item["sku"],
                barcode=item["barcode"],
                description="Produto fictício criado via comando seed-demo.",
                category_id=cat.id,
                unit=item["unit"],
                unit_cost=item["unit_cost"],
                min_stock=item["min_stock"],
                safety_stock=item["safety_stock"],
                current_stock=Decimal("0.000"),
                location=item["location"],
                preferred_supplier_id=sup.id,
                lead_time_days=item["lead_time"],
                is_active=True,
            )
            db.add(prod)
            db.flush()

            balance = Decimal("0.000")
            open_stockout: StockoutPeriod | None = None
            for offset_days, mv_type, reason, qty, u_cost, ord_off, rec_off, note in item["events"]:
                ev_time = (now_local + timedelta(days=offset_days)).astimezone(timezone.utc)
                signed = qty if mv_type == "ENTRADA" else -qty
                before = balance
                after = before + signed
                balance = after

                order_d = (
                    (now_local + timedelta(days=ord_off)).date()
                    if ord_off is not None
                    else None
                )
                rec_d = (
                    (now_local + timedelta(days=rec_off)).date()
                    if rec_off is not None
                    else None
                )
                mv = StockMovement(
                    product_id=prod.id,
                    movement_type=mv_type,
                    reason_code=reason,
                    is_demand=(mv_type == "SAIDA" and reason in ("VENDA", "CONSUMO")),
                    quantity=qty,
                    signed_quantity=signed,
                    unit_snapshot=prod.unit,
                    balance_before=before,
                    balance_after=after,
                    unit_cost=u_cost,
                    supplier_id=sup.id if mv_type == "ENTRADA" else None,
                    order_date=order_d,
                    received_date=rec_d,
                    user_id=actor.id,
                    notes=f"[DEMO] {note}",
                    is_synthetic=True,
                    created_at=ev_time,
                )
                db.add(mv)
                db.flush()

                if before > Decimal("0") and after == Decimal("0"):
                    open_stockout = StockoutPeriod(
                        product_id=prod.id,
                        started_at=ev_time,
                        start_movement_id=mv.id,
                    )
                    db.add(open_stockout)
                elif before == Decimal("0") and after > Decimal("0") and open_stockout:
                    open_stockout.ended_at = ev_time
                    open_stockout.end_movement_id = mv.id
                    open_stockout = None

            prod.current_stock = balance
            created_count += 1

        db.commit()
        print(
            f"Seed de demonstração concluído sem sobrescrever dados existentes. "
            f"Novos produtos fictícios criados: {created_count}."
        )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Comandos administrativos do Sistema de Gestão de Estoque.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_admin = sub.add_parser("create-admin", help="Cria um usuário administrador.")
    p_admin.add_argument("--name", required=True, help="Nome completo")
    p_admin.add_argument("--email", required=True, help="E-mail de acesso")
    p_admin.add_argument("--password", required=True, help="Senha (mínimo 6 caracteres)")

    sub.add_parser(
        "seed-demo",
        help="Insere dados fictícios de demonstração sem apagar dados existentes.",
    )

    args = parser.parse_args()
    if args.command == "create-admin":
        return cmd_create_admin(args.name, args.email, args.password)
    if args.command == "seed-demo":
        return cmd_seed_demo()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
