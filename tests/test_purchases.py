from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from baynex_stationery.db.base import Base
from baynex_stationery.db.models import JournalEntry, Product, Warehouse
from baynex_stationery.services.inventory import get_stock_balance
from baynex_stationery.services.treasury import create_treasury_account
from baynex_stationery.services.purchases import (
    create_purchase,
    create_supplier,
    list_purchases,
    post_purchase,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_purchase_draft_does_not_change_stock_and_post_receives_it(session):
    warehouse = Warehouse(code="MAIN", name="المستودع", is_default=True)
    product = Product(sku="P-1", name="دفتر", cost_price=Decimal("2.00"), sale_price=Decimal("4.00"))
    session.add_all([warehouse, product])
    supplier = create_supplier(session, code="SUP-1", name="مورد تجريبي")
    session.flush()
    purchase = create_purchase(
        session, number="PUR-1", supplier_id=supplier.id, warehouse_id=warehouse.id,
        lines=[{"product_id": product.id, "quantity": "5", "unit_cost": "3.00", "discount": "2.00"}],
        paid_amount="4.00",
    )
    assert get_stock_balance(session, product.id, warehouse.id) == Decimal("0.000")
    post_purchase(session, purchase_id=purchase.id)
    assert get_stock_balance(session, product.id, warehouse.id) == Decimal("5.000")
    assert product.cost_price == Decimal("2.60")
    assert purchase.discount == Decimal("2.00")
    assert purchase.total == Decimal("13.00")
    assert purchase.status == "posted"
    assert purchase.paid_amount == Decimal("4.00")
    assert len(list_purchases(session, status="posted")) == 1
    journal = session.scalar(select(JournalEntry).where(JournalEntry.source_type == "purchase", JournalEntry.source_id == purchase.id))
    assert journal is not None and journal.status == "posted"
    assert sum((line.debit for line in journal.lines), Decimal("0.00")) == Decimal("13.00")
    assert sum((line.credit for line in journal.lines), Decimal("0.00")) == Decimal("13.00")


def test_purchase_cannot_be_posted_twice(session):
    warehouse = Warehouse(code="MAIN", name="المستودع", is_default=True)
    product = Product(sku="P-2", name="قلم", cost_price=Decimal("1.00"), sale_price=Decimal("2.00"))
    session.add_all([warehouse, product])
    supplier = create_supplier(session, code="SUP-2", name="مورد")
    session.flush()
    purchase = create_purchase(
        session, number="PUR-2", supplier_id=supplier.id, warehouse_id=warehouse.id,
        lines=[{"product_id": product.id, "quantity": "2", "unit_cost": "1.00"}],
    )
    post_purchase(session, purchase_id=purchase.id)
    with pytest.raises(ValueError, match="سبق ترحيلها"):
        post_purchase(session, purchase_id=purchase.id)
    assert get_stock_balance(session, product.id, warehouse.id) == Decimal("2.000")


def test_purchase_rejects_overpayment(session):
    warehouse = Warehouse(code="MAIN", name="المستودع", is_default=True)
    product = Product(sku="P-3", name="ممحاة", cost_price=Decimal("1.00"), sale_price=Decimal("2.00"))
    session.add_all([warehouse, product])
    supplier = create_supplier(session, code="SUP-3", name="مورد")
    session.flush()
    with pytest.raises(ValueError, match="يتجاوز"):
        create_purchase(
            session, number="PUR-3", supplier_id=supplier.id, warehouse_id=warehouse.id,
            lines=[{"product_id": product.id, "quantity": "1", "unit_cost": "2.00"}],
            paid_amount="3.00",
        )

def test_purchase_payment_uses_the_only_active_cashbox_ledger(session):
    warehouse = Warehouse(code="CASH-PUR", name="مستودع", is_default=True)
    product = Product(
        sku="CASH-PUR-01", name="قلم", cost_price=Decimal("1.00"),
        sale_price=Decimal("2.00"),
    )
    session.add_all([warehouse, product])
    supplier = create_supplier(session, code="CASH-SUP", name="مورد")
    cashbox = create_treasury_account(
        session, code="PUR-CASH", name="صندوق المشتريات",
        account_kind="cash", ledger_code="1002",
    )
    purchase = create_purchase(
        session, number="PUR-CASH-001", supplier_id=supplier.id,
        warehouse_id=warehouse.id,
        lines=[{"product_id": product.id, "quantity": "2", "unit_cost": "3.00"}],
        paid_amount="2.00", payment_method="cash",
    )
    post_purchase(session, purchase_id=purchase.id)
    journal = session.scalar(select(JournalEntry).where(
        JournalEntry.source_type == "purchase", JournalEntry.source_id == purchase.id,
    ))
    assert any(
        line.account_id == cashbox.ledger_account_id and line.credit == Decimal("2.00")
        for line in journal.lines
    )
