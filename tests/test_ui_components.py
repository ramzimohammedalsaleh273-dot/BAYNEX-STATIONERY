"""Tests for reusable BAYNEX Qt presentation components."""

import os
from datetime import datetime
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QGroupBox, QLabel, QTableWidget

from baynex_stationery.ui.components import configure_data_table, create_page_heading
from baynex_stationery.ui.main_window import InventoryMovementsDialog, ProductDialog

_APP = None


def _application():
    global _APP
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_page_heading_has_consistent_accessible_object_names():
    _application()
    heading = create_page_heading("إدارة الأصناف", "بيانات الأصناف والمخزون")

    assert heading.objectName() == "pageHeading"
    labels = heading.findChildren(QLabel)
    assert [label.objectName() for label in labels] == ["pageTitle", "pageSubtitle"]


def test_data_table_configuration_preserves_rows_and_sets_readable_defaults():
    _application()
    table = QTableWidget(2, 3)

    configure_data_table(table, row_height=41)

    assert table.rowCount() == 2
    assert table.columnCount() == 3
    assert table.alternatingRowColors()
    assert not table.verticalHeader().isVisible()
    assert table.verticalHeader().defaultSectionSize() == 41
    assert table.horizontalHeader().minimumHeight() == 42
    assert table.horizontalHeader().stretchLastSection()


def test_product_dialog_groups_related_fields_without_losing_them():
    _application()
    dialog = ProductDialog([], [])

    assert {group.title() for group in dialog.findChildren(QGroupBox)} == {
        "البيانات الأساسية",
        "الأسعار والكميات",
        "التصنيف ووحدة القياس",
    }
    assert set(dialog.fields) == {
        "sku", "name", "barcode", "sale", "cost", "stock", "minimum", "notes"
    }


def test_inventory_movements_dialog_renders_real_movement_rows():
    _application()
    movement = SimpleNamespace(
        created_at=datetime(2026, 11, 11, 14, 30),
        movement_type="receipt",
        quantity_delta=5,
        note="إدخال اختبار",
    )
    dialog = InventoryMovementsDialog([movement])

    assert dialog.table.rowCount() == 1
    assert dialog.table.columnCount() == 4
    assert dialog.table.item(0, 1).text() == "إدخال"
    assert dialog.table.item(0, 2).text() == "+5"
    assert dialog.table.item(0, 3).text() == "إدخال اختبار"



def test_main_window_has_enterprise_header_grouped_actions_and_real_menus():
    _application()
    from baynex_stationery.ui.main_window import MainWindow

    window = MainWindow()
    assert window.findChild(QLabel, "brandName").text() == "BAYNEX"
    groups = {group.title() for group in window.findChildren(QGroupBox)}
    assert "إدارة الأصناف والتعريفات" in groups
    assert "عمليات المستودعات والمخزون" in groups
    assert "سجل الأصناف وأرصدة المستودع" in groups
    assert [action.text() for action in window.menuBar().actions()] == [
        "ملف", "الأصناف", "المخزون", "مساعدة"
    ]
    window.close()
