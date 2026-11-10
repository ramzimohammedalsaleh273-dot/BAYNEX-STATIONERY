from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from baynex_stationery.db.base import Base
from baynex_stationery.services.catalog import (
    create_category,
    create_unit,
    list_categories,
    list_units,
)
from baynex_stationery.services.products import (
    create_product,
    get_product_by_barcode,
    list_products,
    set_product_active,
    update_product,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_categories_and_units_are_persisted(session):
    category = create_category(session, "دفاتر", "دفاتر مدرسية")
    unit = create_unit(session, "قطعة", "قطعة")
    session.commit()
    assert [item.name for item in list_categories(session)] == ["دفاتر"]
    assert [item.symbol for item in list_units(session)] == ["قطعة"]
    assert category.id and unit.id


def test_category_and_unit_require_names(session):
    with pytest.raises(ValueError):
        create_category(session, "  ")
    with pytest.raises(ValueError):
        create_unit(session, "علبة", " ")


def test_product_category_unit_barcode_and_low_stock_search(session):
    category = create_category(session, "أقلام")
    unit = create_unit(session, "علبة", "علبة")
    product = create_product(
        session, sku="PEN-01", name="قلم أزرق", sale_price=Decimal(5),
        opening_stock=Decimal(2), minimum_stock=Decimal(3),
        barcode="6281234567890", category_id=category.id, unit_id=unit.id,
    )
    session.commit()
    assert product.unit == "علبة"
    assert product.category.name == "أقلام"
    assert get_product_by_barcode(session, " 6281234567890 ").id == product.id
    assert [p.id for p in list_products(session, search="628123")] == [product.id]
    assert [p.id for p in list_products(session, category_id=category.id)] == [product.id]
    assert [p.id for p in list_products(session, low_stock_only=True)] == [product.id]


def test_duplicate_barcode_is_rejected_by_database(session):
    create_product(session, sku="A", name="أ", sale_price=Decimal(1), barcode="123")
    create_product(session, sku="B", name="ب", sale_price=Decimal(1), barcode="123")
    with pytest.raises(IntegrityError):
        session.flush()


def test_product_update_and_soft_deactivation(session):
    product = create_product(session, sku="OLD", name="قديم", sale_price=Decimal(1))
    session.flush()
    update_product(session, product.id, sku="NEW", name="جديد", sale_price=Decimal(2))
    session.commit()
    assert list_products(session)[0].name == "جديد"
    set_product_active(session, product.id, False)
    session.commit()
    assert list_products(session) == []
    assert list_products(session, include_inactive=True)[0].sku == "NEW"


def test_invalid_category_and_unit_are_rejected(session):
    with pytest.raises(ValueError, match="التصنيف"):
        create_product(session, sku="X", name="صنف", sale_price=Decimal(1), category_id=999)
    with pytest.raises(ValueError, match="الوحدة"):
        create_product(session, sku="Y", name="صنف", sale_price=Decimal(1), unit_id=999)


@pytest.mark.parametrize("field,value", [
    ("minimum_stock", Decimal(-1)),
    ("minimum_stock", Decimal("1.0001")),
    ("sale_price", Decimal("NaN")),
])
def test_update_rejects_invalid_values(session, field, value):
    product = create_product(session, sku="U", name="صنف", sale_price=Decimal(1))
    with pytest.raises(ValueError):
        update_product(session, product.id, **{field: value})
