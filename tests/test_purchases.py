from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from baynex_stationery.db.base import Base
from baynex_stationery.db.models import Product, Warehouse
from baynex_stationery.services.inventory import get_stock_balance
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
        lines=[{"product_id": product.id, "quantity": "5", "unit_cost": "3.00"}],
        paid_amount="4.00",
    )
    assert get_stock_balance(session, product.id, warehouse.id) == Decimal("0.000")
    post_purchase(session, purchase_id=purchase.id)
    assert get_stock_balance(session, product.id, warehouse.id) == Decimal("5.000")
    assert product.cost_price == Decimal("3.00")
    assert purchase.status == "posted"
    assert purchase.paid_amount == Decimal("4.00")
    assert len(list_purchases(session, status="posted")) == 1


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
