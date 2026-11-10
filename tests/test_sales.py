from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from baynex_stationery.db.base import Base
from baynex_stationery.db.models import Payment, Product, Sale, SaleItem, StockMovement, UnitOfMeasure
from baynex_stationery.services.sales import post_sale


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def make_product(session, stock="10"):
    unit = UnitOfMeasure(code="PCS", name="قطعة", symbol="قطعة", decimal_places=0)
    session.add(unit)
    session.flush()
    product = Product(
        sku="P-001", name="دفتر", unit="قطعة", unit_record=unit,
        cost_price=Decimal(2), sale_price=Decimal(5),
        stock_quantity=Decimal(stock), minimum_stock=Decimal(0),
    )
    session.add(product)
    session.flush()
    return product


def test_post_sale_decrements_stock_and_records_documents(session):
    product = make_product(session)
    sale = post_sale(
        session, number="INV-001",
        items=[{"product_id": product.id, "quantity": "2"}],
        tax_rate=Decimal("0.15"),
    )
    session.commit()

    assert sale.total == Decimal("11.50")
    assert product.stock_quantity == Decimal(8)
    assert len(list(session.scalars(select(SaleItem)))) == 1
    movement = session.scalar(select(StockMovement))
    assert movement.quantity_delta == Decimal("-2.000")
    assert session.scalar(select(Payment)).amount == Decimal("11.50")


def test_sale_rejects_insufficient_stock_without_creating_sale(session):
    product = make_product(session, stock="1")
    with pytest.raises(ValueError, match="الرصيد غير كافٍ"):
        post_sale(
            session, number="INV-002",
            items=[{"product_id": product.id, "quantity": "2"}],
        )
    assert product.stock_quantity == Decimal(1)
    assert session.scalar(select(Sale)) is None


def test_sale_rejects_empty_lines(session):
    with pytest.raises(ValueError, match="صنف واحد"):
        post_sale(session, number="INV-003", items=[])
