from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from baynex_stationery.db.base import Base
from baynex_stationery.services.catalog import (
    create_category,
    create_unit,
    list_categories,
    list_units,
    set_category_active,
)
from baynex_stationery.services.products import (
    add_product_barcode,
    archive_product,
    create_product,
    find_product_by_barcode,
    list_products,
    update_product,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()

def test_category_hierarchy_and_case_insensitive_duplicates(session):
    parent = create_category(session, name="أدوات مدرسية")
    child = create_category(session, name="أقلام", parent_id=parent.id)
    session.commit()
    assert child.parent_id == parent.id
    with pytest.raises(ValueError, match="مستخدم"):
        create_category(session, name="أدوات مدرسية")
    assert len(list_categories(session)) == 2

def test_category_deactivation(session):
    category = create_category(session, name="دفاتر")
    set_category_active(session, category.id, False)
    session.commit()
    assert list_categories(session) == []
    assert len(list_categories(session, include_inactive=True)) == 1

def test_unit_validation_and_duplicates(session):
    unit = create_unit(session, code="PK", name="باكيت", symbol="باكيت", decimal_places=0)
    assert unit.id is not None
    with pytest.raises(ValueError, match="مستخدم"):
        create_unit(session, code="pk", name="حزمة", symbol="حزمة")
    with pytest.raises(ValueError, match="بين صفر وثلاث"):
        create_unit(session, code="BAD", name="وحدة خاطئة", symbol="خ", decimal_places=4)
    assert list_units(session)[0].name == "باكيت"

def test_product_category_unit_and_multiple_barcodes(session):
    category = create_category(session, name="أقلام")
    create_unit(session, code="BOX", name="علبة", symbol="علبة", decimal_places=0)
    product = create_product(session, sku="pen-01", name="قلم أزرق", sale_price=5,
                              category_id=category.id, unit="علبة", barcode="6281234567890")
    add_product_barcode(session, product.id, "PEN-ALT-001")
    session.commit()
    assert product.sku == "PEN-01"
    assert product.unit_record.name == "علبة"
    assert product.category.name == "أقلام"
    assert find_product_by_barcode(session, "pen-alt-001").id == product.id
    assert len(list_products(session, search="PEN-ALT")) == 1
    assert len(list_products(session, category_id=category.id)) == 1

def test_quantity_precision_follows_the_selected_unit(session):
    create_unit(session, code="M", name="متر", symbol="م", decimal_places=3)
    product = create_product(
        session, sku="M-001", name="سلك", sale_price=2,
        unit="متر", opening_stock="1.234",
    )
    assert product.stock_quantity == Decimal("1.234")
    with pytest.raises(ValueError, match="حسب الوحدة"):
        create_product(
            session, sku="PCS-001", name="قلم", sale_price=2,
            unit="قطعة", opening_stock="1.5",
        )


def test_duplicate_barcodes_are_rejected_case_insensitively(session):
    create_product(session, sku="A-1", name="صنف أول", sale_price=1, barcode="ABC-123")
    with pytest.raises(ValueError, match="الباركود مستخدم"):
        create_product(session, sku="A-2", name="صنف ثان", sale_price=1, barcode="abc-123")
    with pytest.raises(ValueError, match="الباركود مستخدم"):
        add_product_barcode(session, 1, "AbC-123")

def test_update_and_archive_product(session):
    product = create_product(session, sku="OLD-1", name="قديم", sale_price=2)
    update_product(session, product.id, sku="NEW-1", name="جديد", sale_price=3)
    session.commit()
    assert list_products(session)[0].name == "جديد"
    archive_product(session, product.id)
    session.commit()
    assert list_products(session) == []
    assert len(list_products(session, include_inactive=True)) == 1
