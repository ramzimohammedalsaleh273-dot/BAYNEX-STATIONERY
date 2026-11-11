from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from baynex_stationery.db.base import Base
from baynex_stationery.db.models import Product
from baynex_stationery.services.products import create_product, list_products


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_create_and_list_product(session):
    product = create_product(
        session,
        sku="NOTE-001",
        name="دفتر",
        sale_price=Decimal("12.50"),
        cost_price=Decimal("8.00"),
        opening_stock=Decimal(15),
        barcode="628000000001",
    )
    session.commit()

    products = list_products(session)
    assert len(products) == 1
    assert products[0].id == product.id
    assert products[0].name == "دفتر"
    assert products[0].stock_quantity == Decimal("15.000")
    assert session.scalar(select(Product).where(Product.sku == "NOTE-001")) is not None


@pytest.mark.parametrize(
    ("sku", "name", "sale_price", "cost_price", "opening_stock"),
    [
        ("", "دفتر", Decimal(1), Decimal(1), Decimal(1)),
        ("SKU-2", " ", Decimal(1), Decimal(1), Decimal(1)),
        ("SKU-3", "قلم", Decimal(-1), Decimal(1), Decimal(1)),
        ("SKU-4", "قلم", Decimal(1), Decimal(-1), Decimal(1)),
        ("SKU-5", "قلم", Decimal(1), Decimal(1), Decimal(-1)),
    ],
)
def test_create_product_rejects_invalid_values(
    session, sku, name, sale_price, cost_price, opening_stock
):
    with pytest.raises(ValueError):
        create_product(
            session,
            sku=sku,
            name=name,
            sale_price=sale_price,
            cost_price=cost_price,
            opening_stock=opening_stock,
        )


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity")])
def test_create_product_rejects_non_finite_price(session, value):
    with pytest.raises(ValueError, match="محدوداً"):
        create_product(
            session,
            sku="INVALID-PRICE",
            name="صنف غير صالح",
            sale_price=value,
        )


def test_create_product_rejects_excess_stock_precision(session):
    with pytest.raises(ValueError, match="ثلاث خانات"):
        create_product(
            session,
            sku="INVALID-STOCK",
            name="رصيد غير صالح",
            sale_price=Decimal(1),
            opening_stock=Decimal("1.0001"),
        )




def test_create_product_stores_optional_wholesale_price(session):
    product = create_product(
        session, sku="WHOLE-001", name="دفتر جملة",
        sale_price=Decimal("10.00"), wholesale_price=Decimal("8.50"),
    )
    assert product.sale_price == Decimal("10.00")
    assert product.wholesale_price == Decimal("8.50")


def test_create_product_allows_no_wholesale_price(session):
    product = create_product(
        session, sku="RETAIL-001", name="قلم تجزئة",
        sale_price=Decimal("4.00"),
    )
    assert product.wholesale_price is None


def test_create_product_rejects_invalid_wholesale_price(session):
    with pytest.raises(ValueError, match="سعر الجملة"):
        create_product(
            session, sku="WHOLE-BAD", name="صنف",
            sale_price=Decimal("4.00"), wholesale_price=Decimal("-1.00"),
        )
