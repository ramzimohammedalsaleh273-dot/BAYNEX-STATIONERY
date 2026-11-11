"""Tests for reusable BAYNEX Qt presentation components."""

import os

from PySide6.QtWidgets import QApplication, QGroupBox, QLabel, QTableWidget

from baynex_stationery.ui.components import configure_data_table, create_page_heading
from baynex_stationery.ui.main_window import ProductDialog


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
