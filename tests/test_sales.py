from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from baynex_stationery.db.base import Base
from baynex_stationery.db.models import JournalEntry, Payment, Product, Sale, SaleItem, StockMovement
from baynex_stationery.services.inventory import (
    create_warehouse,
    ensure_default_warehouse,
    get_stock_balance,
    record_stock_movement,
)
from baynex_stationery.services.products import create_product
from baynex_stationery.services.sales import create_sale, list_sales, post_sale


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def make_product(session, stock="10"):
    product = Product(
        sku="P-001", name="دفتر", unit="قطعة",
        cost_price=Decimal(2), sale_price=Decimal(5),
        stock_quantity=Decimal(stock), minimum_stock=Decimal(0),
    )
    session.add(product)
    session.flush()
    if Decimal(stock) > 0:
        warehouse = ensure_default_warehouse(session)
        record_stock_movement(
            session, product_id=product.id, warehouse_id=warehouse.id,
            quantity_delta=Decimal(stock), movement_type="opening",
            reference_type="test", reference_id=product.id,
        )
    else:
        ensure_default_warehouse(session)
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
    movement = session.scalar(select(StockMovement).where(StockMovement.movement_type == "sale"))
    assert movement.quantity_delta == Decimal("-2.000")
    assert session.scalar(select(Payment)).amount == Decimal("11.50")
    journal = session.scalar(select(JournalEntry).where(JournalEntry.source_type == "sale", JournalEntry.source_id == sale.id))
    assert journal is not None and journal.status == "posted"
    assert sum((line.debit for line in journal.lines), Decimal("0.00")) == Decimal("11.50")
    assert sum((line.credit for line in journal.lines), Decimal("0.00")) == Decimal("11.50")


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



def test_sale_uses_selected_warehouse_balance_only(session):
    product = make_product(session, stock="0")
    main = ensure_default_warehouse(session)
    branch = create_warehouse(session, code="SALE-BR", name="مستودع البيع")
    record_stock_movement(
        session, product_id=product.id, warehouse_id=branch.id,
        quantity_delta=Decimal(5), movement_type="opening",
        reference_type="test", reference_id=product.id,
    )
    with pytest.raises(ValueError, match="الرصيد غير كافٍ"):
        post_sale(
            session, number="INV-BR-FAIL",
            items=[{"product_id": product.id, "quantity": "1"}],
            warehouse_id=main.id,
        )
    sale = post_sale(
        session, number="INV-BR-OK",
        items=[{"product_id": product.id, "quantity": "2"}],
        warehouse_id=branch.id,
    )
    assert sale.warehouse_id == branch.id
    assert product.stock_quantity == Decimal("3.000")




def test_sale_draft_keeps_unit_quantity_price_and_does_not_touch_stock(session):
    warehouse = ensure_default_warehouse(session)
    product = create_product(
        session, sku="DRAFT-01", name="قلم أزرق",
        sale_price=Decimal("10.00"), cost_price=Decimal("6.00"),
    )
    record_stock_movement(
        session, product_id=product.id, warehouse_id=warehouse.id,
        quantity_delta=Decimal(20), movement_type="opening",
        reference_type="test", reference_id=product.id,
    )
    sale = create_sale(
        session, number="SL-DRAFT-001", warehouse_id=warehouse.id,
        customer_name="مكتبة النور",
        lines=[{"product_id": product.id, "quantity": "2.500", "unit_price": "12.00"}],
    )
    assert sale.status == "draft"
    assert sale.items[0].product_name == "قلم أزرق"
    assert sale.items[0].product_sku == "DRAFT-01"
    assert sale.items[0].unit_name == "قطعة"
    assert sale.items[0].quantity == Decimal("2.500")
    assert sale.items[0].line_total == Decimal("30.00")
    assert get_stock_balance(session, product.id, warehouse.id) == Decimal("20.000")


def test_posted_invoice_records_fractional_quantity_and_payment_once(session):
    warehouse = ensure_default_warehouse(session)
    product = make_product(session)
    sale = create_sale(
        session, number="SL-NEW-002", warehouse_id=warehouse.id,
        lines=[{"product_id": product.id, "quantity": "1.250", "unit_price": "10.00"}],
        paid_amount="5.00",
    )
    post_sale(session, sale_id=sale.id)
    assert sale.status == "posted"
    assert get_stock_balance(session, product.id, warehouse.id) == Decimal("8.750")
    payments = list(session.scalars(select(Payment).where(Payment.sale_id == sale.id)))
    assert len(payments) == 1
    with pytest.raises(ValueError, match="سبق ترحيلها"):
        post_sale(session, sale_id=sale.id)
    assert len(list(session.scalars(select(Payment).where(Payment.sale_id == sale.id)))) == 1


def test_sales_history_searches_invoice_number_and_customer(session):
    product = make_product(session)
    warehouse = ensure_default_warehouse(session)
    create_sale(
        session, number="SL-2026-001", warehouse_id=warehouse.id,
        customer_name="مكتبة النور",
        lines=[{"product_id": product.id, "quantity": "1"}],
    )
    assert len(list_sales(session, search="النور")) == 1
    assert len(list_sales(session, search="2026-001")) == 1
    assert list_sales(session, search="غير موجود") == []
