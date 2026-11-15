"""Application entry point."""
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from baynex_stationery.db.session import initialize_database
from baynex_stationery.ui.main_window import MainWindow


def run() -> int:
    initialize_database()
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setApplicationName("BAYNEX STATIONERY")
    window = MainWindow()
    window.show()
    return app.exec()
