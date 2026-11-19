"""Shared modern visual language for the BAYNEX Arabic desktop ERP."""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

BAYNEX_STYLESHEET = """
QWidget {
    color: #172B3A;
    font-family: "Segoe UI", "Noto Sans Arabic", sans-serif;
    font-size: 10pt;
}
QMainWindow, QDialog, QWidget#centralwidget, QWidget#applicationRoot {
    background: #F3F6FA;
}
QMenuBar {
    color: #243B4D;
    background: #FFFFFF;
    border-bottom: 1px solid #DCE4EC;
    padding: 5px 8px;
}
QMenuBar::item {
    background: transparent;
    padding: 7px 12px;
    border-radius: 6px;
}
QMenuBar::item:selected { background: #EAF2F8; color: #145A82; }
QToolBar {
    spacing: 7px;
    background: #FFFFFF;
    border: 0;
    border-bottom: 1px solid #DCE4EC;
    padding: 8px 12px;
}
QToolBar::separator {
    background: #DCE4EC;
    width: 1px;
    margin: 5px 7px;
}
QFrame#brandBar {
    background: #123B56;
    border: 0;
    border-radius: 10px;
}
QLabel#brandName {
    color: #FFFFFF;
    font-size: 19pt;
    font-weight: 800;
}
QLabel#brandCaption { color: #D5E6F1; }
QLabel#brandVersion {
    color: #FFFFFF;
    background: #245C7B;
    border: 1px solid #477D9A;
    border-radius: 7px;
    padding: 5px 10px;
}
QLabel { background: transparent; }
QLabel#pageTitle {
    color: #123B56;
    font-size: 17pt;
    font-weight: 750;
    padding: 3px 1px;
}
QLabel#pageSubtitle {
    color: #637789;
    font-size: 9pt;
    padding: 0 2px 5px 2px;
}
QWidget#pageHeading { background: transparent; }
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox,
QTextEdit, QPlainTextEdit {
    color: #1D3445;
    background: #FFFFFF;
    border: 1px solid #CBD6E0;
    border-radius: 7px;
    padding: 7px 10px;
    min-height: 25px;
    selection-background-color: #CDE6F5;
}
QLineEdit:hover, QComboBox:hover, QDateEdit:hover,
QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #9CB8CA;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {
    border: 1px solid #2382B5;
    background: #FFFFFF;
}
QPushButton {
    color: #294354;
    background: #FFFFFF;
    border: 1px solid #C9D6E0;
    border-radius: 7px;
    padding: 7px 13px;
    min-height: 27px;
    font-weight: 600;
}
QPushButton:hover {
    background: #F0F7FB;
    border-color: #91B8CE;
}
QPushButton:pressed {
    background: #DCECF5;
    border-color: #6D9DB8;
}
QPushButton:disabled {
    color: #9AA8B3;
    background: #EEF1F4;
    border-color: #E0E6EB;
}
QPushButton#primaryAction {
    color: #FFFFFF;
    background: #176B96;
    border: 1px solid #176B96;
    font-weight: 700;
}
QPushButton#primaryAction:hover { background: #125B82; border-color: #125B82; }
QPushButton#primaryAction:pressed { background: #0F4B6C; }
QComboBox::drop-down { border: 0; width: 25px; }
QTableWidget, QTableView {
    color: #243B4D;
    background: #FFFFFF;
    alternate-background-color: #F7FAFC;
    border: 1px solid #D8E2EA;
    border-radius: 8px;
    gridline-color: #E8EEF3;
    selection-background-color: #DCEEF8;
    selection-color: #123B56;
}
QHeaderView::section {
    color: #385367;
    background: #EDF3F7;
    border: 0;
    border-bottom: 1px solid #D8E2EA;
    padding: 9px 8px;
    min-height: 27px;
    font-weight: 700;
}
QTableWidget::item, QTableView::item {
    padding: 6px;
    border-bottom: 1px solid #EEF2F5;
}
QTableWidget::item:selected, QTableView::item:selected {
    background: #DCEEF8;
    color: #123B56;
}
QGroupBox {
    background: #FFFFFF;
    border: 1px solid #DCE5EC;
    border-radius: 9px;
    margin-top: 15px;
    padding: 12px 10px 9px 10px;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    right: 13px;
    padding: 0 7px;
    color: #245873;
    background: #F3F6FA;
}
QStatusBar {
    background: #FFFFFF;
    color: #526A7B;
    border-top: 1px solid #DCE5EC;
    min-height: 27px;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #EEF2F5;
    border: 0;
    width: 12px;
    height: 12px;
    margin: 2px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #B8C8D3;
    border-radius: 5px;
    min-height: 28px;
    min-width: 28px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: #91A9B8;
}
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QToolTip {
    color: #FFFFFF;
    background: #18394F;
    border: 1px solid #18394F;
    border-radius: 5px;
    padding: 5px 7px;
}
QMenu {
    color: #243B4D;
    background: #FFFFFF;
    border: 1px solid #D8E2EA;
    border-radius: 7px;
    padding: 5px;
}
QMenu::item { padding: 7px 24px; border-radius: 4px; }
QMenu::item:selected { background: #EAF2F8; color: #145A82; }
QTabWidget::pane {
    background: #FFFFFF;
    border: 1px solid #D8E2EA;
    border-radius: 7px;
}
QTabBar::tab {
    color: #536B7C;
    background: #EAF0F4;
    border: 1px solid #D8E2EA;
    padding: 8px 15px;
    margin-left: 3px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    color: #145A82;
    background: #FFFFFF;
    border-bottom: 2px solid #2382B5;
    font-weight: 700;
}
QCheckBox, QRadioButton { spacing: 7px; color: #344E60; }
QCheckBox::indicator, QRadioButton::indicator { width: 17px; height: 17px; }
QDialogButtonBox QPushButton { min-width: 92px; }
QLabel#metricValue {
    color: #123B56;
    font-size: 18pt;
    font-weight: 800;
}
QLabel#mutedText { color: #718494; }
"""

def apply_theme(application: QApplication) -> None:
    """Apply the shared modern Arabic-first theme to every application window."""
    application.setFont(QFont("Segoe UI", 10))
    application.setStyle("Fusion")
    application.setStyleSheet(BAYNEX_STYLESHEET)
