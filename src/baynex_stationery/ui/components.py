"""Reusable, data-oriented widgets shared by BAYNEX screens."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
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


def fit_window_to_screen(
    window: QWidget,
    width: int,
    height: int,
    *,
    min_width: int = 760,
    min_height: int = 520,
    margin: int = 32,
) -> None:
    """Keep ERP windows usable within the current Windows work area."""
    screen = window.screen() or QApplication.primaryScreen()
    if screen is None:
        window.setMinimumSize(min_width, min_height)
        window.resize(width, height)
        return
    available = screen.availableGeometry()
    max_width = max(480, available.width() - margin)
    max_height = max(360, available.height() - margin)
    target_width = min(width, max_width)
    target_height = min(height, max_height)
    window.setMinimumSize(min(min_width, target_width), min(min_height, target_height))
    window.resize(target_width, target_height)
