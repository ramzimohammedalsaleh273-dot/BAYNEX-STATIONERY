"""Reusable, data-oriented widgets shared by BAYNEX screens."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QTableView,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)


def create_page_heading(title: str, subtitle: str, parent: QWidget | None = None) -> QWidget:
    """Build a consistent title block for a business screen."""
    container = QWidget(parent)
    container.setObjectName("pageHeading")
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 8)
    layout.setSpacing(3)

    title_label = QLabel(title, container)
    title_label.setObjectName("pageTitle")
    title_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    subtitle_label = QLabel(subtitle, container)
    subtitle_label.setObjectName("pageSubtitle")
    subtitle_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    subtitle_label.setWordWrap(True)

    layout.addWidget(title_label)
    layout.addWidget(subtitle_label)
    return container


def configure_data_table(
    table: QTableWidget | QTableView,
    *,
    stretch_last: bool = True,
    row_height: int = 38,
) -> None:
    """Apply consistent readable defaults without changing table data or edit policy."""
    table.setAlternatingRowColors(True)
    table.setShowGrid(True)
    table.setWordWrap(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.horizontalHeader().setMinimumHeight(42)
    table.horizontalHeader().setDefaultAlignment(
        Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
    )
    table.horizontalHeader().setHighlightSections(False)
    table.horizontalHeader().setStretchLastSection(stretch_last)
    table.setTextElideMode(Qt.TextElideMode.ElideRight)
