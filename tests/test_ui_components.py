"""Tests for reusable BAYNEX Qt presentation components."""

import os

from PySide6.QtWidgets import QApplication, QLabel, QTableWidget

from baynex_stationery.ui.components import configure_data_table, create_page_heading


def _application():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


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
