"""Shared visual language for the BAYNEX desktop application."""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


BAYNEX_STYLESHEET = """
QWidget {
    color: #243247;
    font-family: "Segoe UI", "Noto Sans Arabic", sans-serif;
    font-size: 10pt;
}
QMainWindow, QDialog, QWidget#centralwidget {
    background: #F3F6FA;
}
QLabel {
    background: transparent;
}
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {
    background: #FFFFFF;
    border: 1px solid #C9D4E2;
    border-radius: 5px;
    padding: 7px 9px;
    min-height: 20px;
    selection-background-color: #D8E9F7;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {
    border: 1px solid #2878A8;
}
QPushButton {
    color: #FFFFFF;
    background: #176B87;
    border: 1px solid #145D76;
    border-radius: 5px;
    padding: 7px 13px;
    min-height: 22px;
    font-weight: 600;
}
QPushButton:hover {
    background: #2185A5;
    border-color: #176B87;
}
QPushButton:pressed {
    background: #10556D;
    padding-top: 8px;
    padding-bottom: 6px;
}
QPushButton:disabled {
    color: #8794A5;
    background: #E5EAF0;
    border-color: #D5DDE7;
}
QComboBox::drop-down {
    border: 0;
    width: 24px;
}
QTableWidget, QTableView {
    background: #FFFFFF;
    alternate-background-color: #F5F8FC;
    border: 1px solid #CBD5E1;
    border-radius: 5px;
    gridline-color: #E1E7EF;
    selection-background-color: #DCECF7;
    selection-color: #173B55;
}
QHeaderView::section {
    color: #FFFFFF;
    background: #244B68;
    border: 0;
    border-right: 1px solid #42637D;
    border-bottom: 2px solid #1593A8;
    padding: 9px 7px;
    min-height: 24px;
    font-weight: 700;
}
QTableWidget::item, QTableView::item {
    padding: 6px;
    border-bottom: 1px solid #E8EDF3;
}
QTableWidget::item:selected, QTableView::item:selected {
    background: #DCECF7;
    color: #173B55;
}
QGroupBox {
    background: #FFFFFF;
    border: 1px solid #D6DFE9;
    border-radius: 6px;
    margin-top: 14px;
    padding: 12px 8px 8px 8px;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    right: 12px;
    padding: 0 6px;
    color: #244B68;
}
QStatusBar {
    background: #E9EFF5;
    color: #52657A;
    border-top: 1px solid #D5DEE8;
}
QScrollBar:vertical {
    background: #EDF1F6;
    width: 12px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #B8C7D6;
    border-radius: 5px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #829CB3;
}
QToolTip {
    color: #FFFFFF;
    background: #20384E;
    border: 1px solid #20384E;
    padding: 5px 7px;
}
"""


def apply_theme(application: QApplication) -> None:
    """Apply the shared Arabic-first theme to every application window."""
    application.setFont(QFont("Segoe UI", 10))
    application.setStyle("Fusion")
    application.setStyleSheet(BAYNEX_STYLESHEET)
