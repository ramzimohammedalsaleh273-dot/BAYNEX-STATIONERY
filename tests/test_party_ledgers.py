from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from baynex_stationery.db.base import Base
from baynex_stationery.db.models import JournalEntry, Product
from baynex_stationery.services.customers import create_customer, list_customers
from baynex_stationery.services.inventory import ensure_default_warehouse, record_stock_movement
from baynex_stationery.services.party_ledgers import customer_statement, supplier_statement
from baynex_stationery.services.purchases import create_purchase, create_supplier, post_purchase
from baynex_stationery.services.sales import create_sale, post_sale


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_customer_sale_is_linked_to_customer_subledger(session):
    warehouse = ensure_default_warehouse(session)
    product = Product(
        sku="PARTY-01", name="دفتر", cost_price=Decimal("2.00"),
        sale_price=Decimal("5.00"), stock_quantity=Decimal("5.000"),
    )
    session.add(product)
    session.flush()
    record_stock_movement(
        session, product_id=product.id, warehouse_id=warehouse.id,
        quantity_delta=Decimal("5"), movement_type="opening",
        reference_type="test", reference_id=product.id,
    )
    customer = create_customer(session, code="C-001", name="مكتبة النور", phone="777")
    sale = create_sale(
        session, number="PARTY-SALE-001", warehouse_id=warehouse.id,
        customer_id=customer.id, lines=[{"product_id": product.id, "quantity": "1"}],
    )
    post_sale(session, sale_id=sale.id)
    rows = customer_statement(session, customer_id=customer.id)
    assert len(rows) == 1
    assert rows[0]["debit"] == Decimal("5.00")
    assert rows[0]["balance"] == Decimal("5.00")
    journal = session.scalar(select(JournalEntry).where(JournalEntry.source_type == "sale"))
    assert any(line.customer_id == customer.id for line in journal.lines)
    assert sale.customer_name == "مكتبة النور"


def test_supplier_purchase_is_linked_to_supplier_subledger(session):
    from baynex_stationery.db.models import Warehouse

    warehouse = Warehouse(code="SUP-WH", name="مستودع", is_default=True)
    product = Product(sku="SUP-PARTY-01", name="قلم", cost_price=Decimal("1"), sale_price=Decimal("2"))
    session.add_all([warehouse, product])
    supplier = create_supplier(session, code="SUP-001", name="مورد الأقلام")
    purchase = create_purchase(
        session, number="PARTY-PUR-001", supplier_id=supplier.id,
        warehouse_id=warehouse.id,
        lines=[{"product_id": product.id, "quantity": "2", "unit_cost": "3.00"}],
    )
    post_purchase(session, purchase_id=purchase.id)
    rows = supplier_statement(session, supplier_id=supplier.id)
    assert len(rows) == 1
    assert rows[0]["credit"] == Decimal("6.00")
    assert rows[0]["balance"] == Decimal("6.00")
    journal = session.scalar(select(JournalEntry).where(JournalEntry.source_type == "purchase"))
    assert any(line.supplier_id == supplier.id for line in journal.lines)


def test_customer_code_is_unique_and_search_is_working(session):
    create_customer(session, code="c-002", name="عميل أول")
    assert [item.name for item in list_customers(session, search="عميل")] == ["عميل أول"]
    with pytest.raises(IntegrityError):
        create_customer(session, code="C-002", name="عميل مكرر")
