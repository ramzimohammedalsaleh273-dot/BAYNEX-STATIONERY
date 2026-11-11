from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from baynex_stationery.db.base import Base
from baynex_stationery.db.models import (
    Product,
    StockMovement,
)
from baynex_stationery.services.inventory import (
    create_inventory_count,
    create_inventory_transfer,
    create_warehouse,
    ensure_default_warehouse,
    get_stock_balance,
    issue_stock,
    list_stock_movements,
    post_inventory_count,
    post_inventory_transfer,
    receive_stock,
    set_inventory_count_line,
    set_warehouse_active,
    update_warehouse,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def make_product(session, sku="P-001"):
    product = Product(
        sku=sku, name=f"صنف {sku}", unit="قطعة",
        cost_price=Decimal(2), sale_price=Decimal(5),
        stock_quantity=Decimal(0), minimum_stock=Decimal(0),
    )
    session.add(product)
    session.flush()
    return product


def test_receipt_issue_and_ledger_balance(session):
    product = make_product(session)
    main = ensure_default_warehouse(session)
    receive_stock(session, product_id=product.id, warehouse_id=main.id, quantity="12.250")
    issue_stock(session, product_id=product.id, warehouse_id=main.id, quantity="2.125")
    session.flush()

    assert get_stock_balance(session, product.id, main.id) == Decimal("10.125")
    assert get_stock_balance(session, product.id) == Decimal("10.125")
    assert product.stock_quantity == Decimal("10.125")
    assert len(list_stock_movements(session, product_id=product.id)) == 2


def test_issue_rejects_negative_balance_without_writing(session):
    product = make_product(session)
    main = ensure_default_warehouse(session)
    with pytest.raises(ValueError, match="الرصيد غير كافٍ"):
        issue_stock(session, product_id=product.id, warehouse_id=main.id, quantity="1")
    assert get_stock_balance(session, product.id, main.id) == Decimal("0.000")
    assert session.scalar(select(StockMovement)) is None


def test_transfer_moves_stock_atomically_between_warehouses(session):
    product = make_product(session)
    main = ensure_default_warehouse(session)
    second = create_warehouse(session, code="BR-01", name="المستودع الفرعي")
    receive_stock(session, product_id=product.id, warehouse_id=main.id, quantity="15")
    transfer = create_inventory_transfer(
        session, number="TR-001", source_warehouse_id=main.id,
        destination_warehouse_id=second.id,
        lines=[{"product_id": product.id, "quantity": "4.500"}],
    )
    assert get_stock_balance(session, product.id, second.id) == Decimal("0.000")
    post_inventory_transfer(session, transfer_id=transfer.id)

    assert get_stock_balance(session, product.id, main.id) == Decimal("10.500")
    assert get_stock_balance(session, product.id, second.id) == Decimal("4.500")
    assert transfer.status == "posted"
    with pytest.raises(ValueError, match="سبق ترحيله"):
        post_inventory_transfer(session, transfer_id=transfer.id)


def test_transfer_rejects_insufficient_source_and_same_warehouse(session):
    product = make_product(session)
    main = ensure_default_warehouse(session)
    second = create_warehouse(session, code="BR-02", name="فرع ثان")
    transfer = create_inventory_transfer(
        session, number="TR-002", source_warehouse_id=main.id,
        destination_warehouse_id=second.id,
        lines=[{"product_id": product.id, "quantity": "1"}],
    )
    with pytest.raises(ValueError, match="الرصيد غير كافٍ"):
        post_inventory_transfer(session, transfer_id=transfer.id)
    assert get_stock_balance(session, product.id) == Decimal("0.000")
    with pytest.raises(ValueError, match="المستودع نفسه"):
        create_inventory_transfer(
            session, number="TR-003", source_warehouse_id=main.id,
            destination_warehouse_id=main.id,
            lines=[{"product_id": product.id, "quantity": "1"}],
        )


def test_count_does_not_change_stock_until_posted_and_cannot_post_twice(session):
    product = make_product(session)
    main = ensure_default_warehouse(session)
    receive_stock(session, product_id=product.id, warehouse_id=main.id, quantity="10")
    count = create_inventory_count(session, number="CO-001", warehouse_id=main.id)
    set_inventory_count_line(
        session, count_id=count.id, product_id=product.id, counted_quantity="8.250"
    )
    assert get_stock_balance(session, product.id, main.id) == Decimal("10.000")
    post_inventory_count(session, count_id=count.id)
    assert get_stock_balance(session, product.id, main.id) == Decimal("8.250")
    assert count.status == "posted"
    with pytest.raises(ValueError, match="سبق ترحيلها"):
        post_inventory_count(session, count_id=count.id)


def test_count_rejects_stale_snapshot(session):
    product = make_product(session)
    main = ensure_default_warehouse(session)
    receive_stock(session, product_id=product.id, warehouse_id=main.id, quantity="10")
    count = create_inventory_count(session, number="CO-002", warehouse_id=main.id)
    set_inventory_count_line(
        session, count_id=count.id, product_id=product.id, counted_quantity="7"
    )
    issue_stock(session, product_id=product.id, warehouse_id=main.id, quantity="1")
    with pytest.raises(ValueError, match="تغير رصيد"):
        post_inventory_count(session, count_id=count.id)
    assert get_stock_balance(session, product.id, main.id) == Decimal("9.000")


def test_default_or_nonempty_warehouse_cannot_be_deactivated(session):
    product = make_product(session)
    main = ensure_default_warehouse(session)
    second = create_warehouse(session, code="BR-03", name="فرع ثالث")
    with pytest.raises(ValueError, match="الافتراضي"):
        set_warehouse_active(session, main.id, False)
    receive_stock(session, product_id=product.id, warehouse_id=second.id, quantity="2")
    with pytest.raises(ValueError, match="رصيد مخزون"):
        set_warehouse_active(session, second.id, False)
    issue_stock(session, product_id=product.id, warehouse_id=second.id, quantity="2")
    set_warehouse_active(session, second.id, False)
    assert second.is_active is False


def test_quantity_precision_is_limited_to_three_decimal_places(session):
    product = make_product(session)
    main = ensure_default_warehouse(session)
    with pytest.raises(ValueError, match="ثلاث خانات"):
        receive_stock(
            session, product_id=product.id, warehouse_id=main.id, quantity="1.0001"
        )



def test_posted_stock_movements_are_immutable(session):
    product = make_product(session)
    main = ensure_default_warehouse(session)
    movement = receive_stock(
        session, product_id=product.id, warehouse_id=main.id, quantity="3"
    )
    movement.note = "محاولة تعديل"
    with pytest.raises(ValueError, match="غير قابلة للتعديل"):
        session.flush()
    session.rollback()


def test_count_rejects_catalog_changes_after_snapshot(session):
    first = make_product(session, "P-101")
    main = ensure_default_warehouse(session)
    receive_stock(session, product_id=first.id, warehouse_id=main.id, quantity="5")
    count = create_inventory_count(session, number="CO-003", warehouse_id=main.id)
    second = make_product(session, "P-102")
    with pytest.raises(ValueError, match="قائمة الأصناف"):
        post_inventory_count(session, count_id=count.id)
    assert get_stock_balance(session, second.id, main.id) == Decimal("0.000")



def test_warehouse_can_be_renamed_and_default_reassigned(session):
    main = ensure_default_warehouse(session)
    second = create_warehouse(session, code="NEW-01", name="مستودع جديد")
    update_warehouse(
        session, second.id, code="NEW-02", name="مستودع معدل", is_default=True
    )
    assert second.code == "NEW-02"
    assert second.name == "مستودع معدل"
    assert second.is_default is True
    assert main.is_default is False
    with pytest.raises(ValueError, match="عيّن مستودعاً افتراضياً"):
        update_warehouse(session, second.id, is_default=False)
