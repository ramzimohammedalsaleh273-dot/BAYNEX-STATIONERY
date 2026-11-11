"""Shared visual language for the BAYNEX desktop application."""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

BAYNEX_STYLESHEET = """
QWidget {
    color: #263746;
    font-family: "Segoe UI", "Noto Sans Arabic", sans-serif;
    font-size: 9pt;
}
QMainWindow, QDialog, QWidget#centralwidget, QWidget#applicationRoot {
    background: #E8EBEF;
}
QMenuBar {
    color: #263746;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F9FAFB, stop:1 #DDE2E7);
    border-bottom: 1px solid #9BA7B2;
    padding: 2px 5px;
}
QMenuBar::item {
    color: #263746;
    background: transparent;
    padding: 5px 11px;
    border: 1px solid transparent;
}
QMenuBar::item:selected {
    background: #D7E8F5;
    border: 1px solid #9BBBD3;
}
QToolBar {
    spacing: 3px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F6F7F8, stop:1 #D9DFE5);
    border: 1px solid #AAB5BF;
    border-left: 0;
    border-right: 0;
    padding: 3px 4px;
}
QToolBar::separator {
    background: #AAB5BF;
    width: 1px;
    margin: 3px 5px;
}
QFrame#brandBar {
    background: #244B68;
    border: 1px solid #183B56;
}
QLabel#brandName {
    color: #FFFFFF;
    font-size: 17pt;
    font-weight: 800;
}
QLabel#brandCaption { color: #E2EDF5; }
QLabel#brandVersion {
    color: #FFFFFF;
    background: #315E7D;
    border: 1px solid #6C8BA4;
    padding: 4px 9px;
}
QLabel { background: transparent; }
QLabel#pageTitle {
    color: #1E4562;
    font-size: 15pt;
    font-weight: 700;
    padding: 2px 1px;
}
QLabel#pageSubtitle {
    color: #526678;
    font-size: 8pt;
    padding: 0 2px 3px 2px;
}
QWidget#pageHeading { background: transparent; }
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {
    color: #263746;
    background: #FFFEEF;
    border: 1px solid #9CAAB6;
    border-radius: 1px;
    padding: 4px 7px;
    min-height: 19px;
    selection-background-color: #C7E0F2;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {
    border: 1px solid #2876A3;
    background: #FFFFFF;
}
QPushButton {
    color: #263746;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 #D7DEE5);
    border: 1px solid #8999A7;
    border-radius: 2px;
    padding: 4px 9px;
    min-height: 19px;
    font-weight: 600;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F4FBFF, stop:1 #C7E1F2);
    border-color: #5B91B7;
}
QPushButton:pressed {
    background: #C1D4E2;
    border-color: #547D9B;
    padding-top: 5px;
    padding-bottom: 3px;
}
QPushButton:disabled {
    color: #8B969F;
    background: #E2E5E8;
    border-color: #C5CCD2;
}
QPushButton#primaryAction {
    color: #163C55;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #EAF6FD, stop:1 #BBD8EA);
    border: 1px solid #6D9FBD;
    font-weight: 750;
}
QPushButton#primaryAction:hover {
    background: #D4ECFA;
}
QComboBox::drop-down { border: 0; width: 22px; }
QTableWidget, QTableView {
    color: #263746;
    background: #FFFFFF;
    alternate-background-color: #F2F5F7;
    border: 1px solid #AAB5BF;
    border-radius: 0;
    gridline-color: #C9D0D6;
    selection-background-color: #C8E0F2;
    selection-color: #163C55;
}
QHeaderView::section {
    color: #263746;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F7F8F9, stop:1 #D6DDE3);
    border: 1px solid #B6C0C8;
    padding: 6px 6px;
    min-height: 22px;
    font-weight: 700;
}
QTableWidget::item, QTableView::item {
    padding: 4px;
    border-bottom: 1px solid #E0E4E8;
}
QTableWidget::item:selected, QTableView::item:selected {
    background: #C8E0F2;
    color: #163C55;
}
QGroupBox {
    background: #F5F6F7;
    border: 1px solid #AEB8C1;
    border-radius: 1px;
    margin-top: 12px;
    padding: 8px 6px 6px 6px;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    right: 10px;
    padding: 0 5px;
    color: #244B68;
}
QStatusBar {
    background: #CDEAF5;
    color: #25465C;
    border-top: 1px solid #8BB9CD;
    min-height: 22px;
}
QScrollBar:vertical {
    background: #E5E9ED;
    width: 12px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #B5C2CC;
    border: 1px solid #97A7B4;
    min-height: 26px;
}
QScrollBar::handle:vertical:hover { background: #9EAFBC; }
QToolTip {
    color: #FFFFFF;
    background: #263F54;
    border: 1px solid #1B354A;
    padding: 4px 6px;
}
QMenu {
    color: #263746;
    background: #F8F9FA;
    border: 1px solid #AAB5BF;
    padding: 3px;
}
QMenu::item { padding: 5px 22px; }
QMenu::item:selected { background: #D7E8F5; color: #163C55; }
QTabWidget::pane { background: #FFFFFF; border: 1px solid #AAB5BF; }
QTabBar::tab {
    color: #344B5D;
    background: #E0E5E9;
    border: 1px solid #AAB5BF;
    padding: 6px 12px;
    margin-left: 2px;
}
QTabBar::tab:selected {
    color: #163C55;
    background: #FFFFFF;
    border-bottom: 2px solid #3183B0;
    font-weight: 700;
}
QCheckBox, QRadioButton { spacing: 6px; color: #34465B; }
QCheckBox::indicator, QRadioButton::indicator { width: 15px; height: 15px; }
QDialogButtonBox QPushButton { min-width: 82px; }
"""


def apply_theme(application: QApplication) -> None:
    """Apply the shared Arabic-first theme to every application window."""
    application.setFont(QFont("Segoe UI", 10))
    application.setStyle("Fusion")
    application.setStyleSheet(BAYNEX_STYLESHEET)
