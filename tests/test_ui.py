import os
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QApplication, QDialog
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from baynex_stationery.db.base import Base
from baynex_stationery.db.models import Product
from baynex_stationery.ui import main_window, pos_dialog


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


@pytest.fixture
def isolated_database(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main_window, "SessionLocal", factory)
    yield factory
    engine.dispose()


def test_add_and_refresh_buttons_use_database(qapp, isolated_database, monkeypatch):
    class AcceptedProductDialog:
        def __init__(self, *_args):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {
                "sku": "UI-001",
                "name": "قلم حبر",
                "sale_price": Decimal("4.50"),
                "cost_price": Decimal("2.00"),
                "opening_stock": Decimal(20),
                "barcode": "",
            }

    monkeypatch.setattr(main_window, "ProductDialog", AcceptedProductDialog)
    window = main_window.MainWindow()
    try:
        window.add_button.click()
        assert window.table.rowCount() == 1
        assert window.table.item(0, 2).text() == "قلم حبر"

        with isolated_database() as session:
            product = session.scalar(select(Product).where(Product.sku == "UI-001"))
            assert product is not None
            assert product.stock_quantity == Decimal("20.000")

        window.refresh_button.click()
        assert window.table.rowCount() == 1
    finally:
        window.close()



def test_pos_grid_locks_catalog_price_and_exposes_cashier_workflows(qapp, isolated_database, monkeypatch):
    monkeypatch.setattr(pos_dialog, "SessionLocal", isolated_database)
    window = pos_dialog.POSDialog()
    try:
        assert window.cart_table.columnCount() == 9
        assert window.cart_table.rowCount() >= 12
        price_flags = window.cart_table.item(0, 6).flags()
        quantity_flags = window.cart_table.item(0, 5).flags()
        discount_flags = window.cart_table.item(0, 7).flags()
        from PySide6.QtCore import Qt
        assert not (price_flags & Qt.ItemFlag.ItemIsEditable)
        assert quantity_flags & Qt.ItemFlag.ItemIsEditable
        assert discount_flags & Qt.ItemFlag.ItemIsEditable
        assert window.hold_button.isVisible() is False or window.hold_button.parent() is not None
        assert window.return_button.text() == "مرتجع مبيعات"
        assert window.history_button.text() == "سجل الكاشير"
    finally:
        window.close()
