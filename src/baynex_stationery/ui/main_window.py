"""Arabic right-to-left desktop shell with a live product register."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from baynex_stationery.db.session import SessionLocal
from baynex_stationery.services.products import create_product, list_products


class ProductDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إضافة صنف")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.fields = {
            "sku": QLineEdit(), "name": QLineEdit(), "sale": QLineEdit("0.00"),
            "cost": QLineEdit("0.00"), "stock": QLineEdit("0"),
            "barcode": QLineEdit(),
        }
        form = QFormLayout()
        for key, label in [
            ("sku", "رمز الصنف *"), ("name", "اسم الصنف *"),
            ("sale", "سعر البيع"), ("cost", "سعر التكلفة"),
            ("stock", "الرصيد الافتتاحي"), ("barcode", "الباركود"),
        ]:
            form.addRow(label, self.fields[key])
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self):
        try:
            return {
                "sku": self.fields["sku"].text(),
                "name": self.fields["name"].text(),
                "sale_price": Decimal(self.fields["sale"].text().strip() or "0"),
                "cost_price": Decimal(self.fields["cost"].text().strip() or "0"),
                "opening_stock": Decimal(self.fields["stock"].text().strip() or "0"),
                "barcode": self.fields["barcode"].text(),
            }
        except InvalidOperation as exc:
            raise ValueError("أدخل أرقاماً صحيحة في حقول الأسعار والكمية") from exc


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BAYNEX STATIONERY | نظام القرطاسية")
        self.resize(1180, 760)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QWidget()
        layout = QVBoxLayout(root)
        header = QLabel("BAYNEX STATIONERY")
        header.setStyleSheet("font-size: 24px; font-weight: 700; padding: 12px;")
        subtitle = QLabel("إدارة القرطاسية والمخزون — إصدار تأسيسي قيد التطوير")
        toolbar = QHBoxLayout()
        self.add_button = QPushButton("إضافة صنف")
        self.refresh_button = QPushButton("تحديث")
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.refresh_button)
        toolbar.addStretch(1)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["الرمز", "الباركود", "اسم الصنف", "الوحدة", "سعر البيع", "الرصيد"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(header)
        layout.addWidget(subtitle)
        layout.addLayout(toolbar)
        layout.addWidget(self.table)
        self.setCentralWidget(root)

        self.add_button.clicked.connect(self.add_product)
        self.refresh_button.clicked.connect(self.refresh_products)
        self.refresh_products()

    def refresh_products(self):
        with SessionLocal() as session:
            products = list_products(session)
            self.table.setRowCount(len(products))
            for row, product in enumerate(products):
                values = [
                    product.sku, product.barcode or "", product.name, product.unit,
                    f"{product.sale_price:.2f}", f"{product.stock_quantity:g}",
                ]
                for column, value in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(str(value)))

    def add_product(self):
        dialog = ProductDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            values = dialog.values()
            with SessionLocal.begin() as session:
                create_product(session, **values)
            self.refresh_products()
        except (ValueError, Exception) as exc:
            QMessageBox.warning(self, "تعذر حفظ الصنف", str(exc))
