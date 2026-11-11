from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from baynex_stationery.db.base import Base
from baynex_stationery.db.models import Payment, Product
from baynex_stationery.services.inventory import (
    ensure_default_warehouse,
    get_stock_balance,
    record_stock_movement,
)
from baynex_stationery.services.pos_workflows import create_sale_return, list_held_sales
from baynex_stationery.services.sales import create_sale, post_sale


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def stocked_sale(session, quantity="5"):
    warehouse = ensure_default_warehouse(session)
    product = Product(
        sku="RET-001", name="دفتر مرتجع", unit="قطعة",
        cost_price=Decimal(2), sale_price=Decimal(5),
        stock_quantity=Decimal(quantity), minimum_stock=Decimal(0),
    )
    session.add(product)
    session.flush()
    record_stock_movement(
        session, product_id=product.id, warehouse_id=warehouse.id,
        quantity_delta=Decimal(quantity), movement_type="opening",
        reference_type="test", reference_id=product.id,
    )
    sale = create_sale(
        session, number="RET-SALE-001", warehouse_id=warehouse.id,
        lines=[{"product_id": product.id, "quantity": quantity}],
        paid_amount=Decimal("25.00"),
    )
    post_sale(session, sale_id=sale.id)
    return sale, product, warehouse


def test_list_held_sales_returns_only_persisted_held_documents(session):
    warehouse = ensure_default_warehouse(session)
    product = Product(sku="HOLD-01", name="قلم", unit="قطعة",
                      cost_price=Decimal(1), sale_price=Decimal(3))
    session.add(product)
    session.flush()
    sale = create_sale(
        session, number="HOLD-INV-01", warehouse_id=warehouse.id,
        lines=[{"product_id": product.id, "quantity": "2"}],
    )
    sale.status = "held"
    session.flush()
    assert [row.number for row in list_held_sales(session)] == ["HOLD-INV-01"]
    assert get_stock_balance(session, product.id, warehouse.id) == Decimal("0.000")


def test_partial_return_restock_and_refund_payment_are_linked(session):
    sale, product, warehouse = stocked_sale(session)
    result = create_sale_return(
        session, number="RET-001", sale_id=sale.id,
        lines=[{"sale_item_id": sale.items[0].id, "quantity": "2.000"}],
        refund_method="cash",
    )
    assert result.sale_id == sale.id
    assert result.refund_amount == Decimal("10.00")
    assert get_stock_balance(session, product.id, warehouse.id) == Decimal("2.000")
    refund = session.scalar(select(Payment).where(Payment.sale_id == sale.id, Payment.amount < 0))
    assert refund.amount == Decimal("-10.00")
    assert refund.method == "refund_cash"


def test_return_cannot_exceed_unreturned_quantity(session):
    sale, _product, _warehouse = stocked_sale(session, quantity="2")
    create_sale_return(
        session, number="RET-002", sale_id=sale.id,
        lines=[{"sale_item_id": sale.items[0].id, "quantity": "1.500"}],
    )
    with pytest.raises(ValueError, match="تتجاوز المتبقي"):
        create_sale_return(
            session, number="RET-003", sale_id=sale.id,
            lines=[{"sale_item_id": sale.items[0].id, "quantity": "1.000"}],
        )



def test_return_cannot_refund_more_than_collected_amount(session):
    warehouse = ensure_default_warehouse(session)
    product = Product(
        sku="CREDIT-01", name="دفتر آجل", unit="قطعة",
        cost_price=Decimal(2), sale_price=Decimal(5),
    )
    session.add(product)
    session.flush()
    record_stock_movement(
        session, product_id=product.id, warehouse_id=warehouse.id,
        quantity_delta=Decimal(2), movement_type="opening",
        reference_type="test", reference_id=product.id,
    )
    sale = create_sale(
        session, number="CREDIT-SALE-01", warehouse_id=warehouse.id,
        lines=[{"product_id": product.id, "quantity": "2"}],
        paid_amount=Decimal("0.00"),
    )
    post_sale(session, sale_id=sale.id)
    with pytest.raises(ValueError, match="لم تُحصّل"):
        create_sale_return(
            session, number="CREDIT-RET-01", sale_id=sale.id,
            lines=[{"sale_item_id": sale.items[0].id, "quantity": "1"}],
        )
