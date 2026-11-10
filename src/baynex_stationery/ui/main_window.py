"""Arabic right-to-left catalog workspace for products, categories and units."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)
from sqlalchemy.exc import SQLAlchemyError
from baynex_stationery.db.session import SessionLocal
from baynex_stationery.services.catalog import create_category, create_unit, list_categories, list_units
from baynex_stationery.services.products import create_product, list_products

class ProductDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إضافة صنف جديد")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.fields = {
            "sku": QLineEdit(), "name": QLineEdit(), "sale": QLineEdit("0.00"),
            "cost": QLineEdit("0.00"), "stock": QLineEdit("0"),
            "minimum": QLineEdit("0"), "barcode": QLineEdit(), "notes": QLineEdit(),
        }
        self.unit_combo = QComboBox()
        self.category_combo = QComboBox()
        with SessionLocal() as session:
            for unit in list_units(session):
                self.unit_combo.addItem(f"{unit.name} ({unit.symbol})", unit.name)
            for category in list_categories(session):
                self.category_combo.addItem(category.name, category.id)
        if self.unit_combo.count() == 0:
            self.unit_combo.addItem("قطعة", "قطعة")
        self.category_combo.insertItem(0, "بدون تصنيف", None)
        form = QFormLayout()
        for key, label in [
            ("sku", "رمز الصنف *"), ("name", "اسم الصنف *"), ("sale", "سعر البيع"),
            ("cost", "سعر التكلفة"), ("stock", "الرصيد الافتتاحي"),
            ("minimum", "حد التنبيه للمخزون"), ("barcode", "الباركود الأساسي"),
            ("notes", "ملاحظات"),
        ]:
            form.addRow(label, self.fields[key])
        form.addRow("الوحدة", self.unit_combo)
        form.addRow("التصنيف", self.category_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self):
        try:
            return {
                "sku": self.fields["sku"].text(), "name": self.fields["name"].text(),
                "sale_price": Decimal(self.fields["sale"].text().strip() or "0"),
                "cost_price": Decimal(self.fields["cost"].text().strip() or "0"),
                "opening_stock": Decimal(self.fields["stock"].text().strip() or "0"),
                "minimum_stock": Decimal(self.fields["minimum"].text().strip() or "0"),
                "barcode": self.fields["barcode"].text(), "notes": self.fields["notes"].text(),
                "unit": self.unit_combo.currentData() or "قطعة",
                "category_id": self.category_combo.currentData(),
            }
        except InvalidOperation as exc:
            raise ValueError("أدخل أرقاماً صحيحة في حقول الأسعار والكميات") from exc

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BAYNEX STATIONERY | نظام القرطاسية")
        self.resize(1320, 820)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QWidget()
        layout = QVBoxLayout(root)
        header = QLabel("BAYNEX STATIONERY")
        header.setStyleSheet("font-size: 24px; font-weight: 700; padding: 12px;")
        subtitle = QLabel("دليل الأصناف والتصنيفات والوحدات والباركود")
        toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ابحث بالاسم أو الرمز أو الباركود...")
        self.add_button = QPushButton("إضافة صنف")
        self.category_button = QPushButton("إضافة تصنيف")
        self.unit_button = QPushButton("إضافة وحدة")
        self.refresh_button = QPushButton("تحديث")
        toolbar.addWidget(self.search_input, 1)
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.category_button)
        toolbar.addWidget(self.unit_button)
        toolbar.addWidget(self.refresh_button)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["الرمز", "الباركود", "اسم الصنف", "الوحدة",
            "سعر البيع", "الرصيد", "التصنيف", "الحالة"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(header)
        layout.addWidget(subtitle)
        layout.addLayout(toolbar)
        layout.addWidget(self.table)
        self.setCentralWidget(root)
        self.add_button.clicked.connect(self.add_product)
        self.category_button.clicked.connect(self.add_category)
        self.unit_button.clicked.connect(self.add_unit)
        self.refresh_button.clicked.connect(self.refresh_products)
        self.search_input.textChanged.connect(self.refresh_products)
        self.refresh_products()

    def refresh_products(self, *_args):
        with SessionLocal() as session:
            products = list_products(session, search=self.search_input.text())
            self.table.setRowCount(len(products))
            for row, product in enumerate(products):
                values = [product.sku, product.barcode or "", product.name, product.unit,
                    f"{product.sale_price:.2f}", f"{product.stock_quantity:g}",
                    product.category.name if product.category else "—",
                    "نشط" if product.is_active else "مؤرشف"]
                for column, value in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(str(value)))

    def add_product(self):
        dialog = ProductDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with SessionLocal.begin() as session:
                create_product(session, **dialog.values())
            self.refresh_products()
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر حفظ الصنف", str(exc))

    def add_category(self):
        name, accepted = QInputDialog.getText(self, "تصنيف جديد", "اسم التصنيف:")
        if not accepted:
            return
        try:
            with SessionLocal.begin() as session:
                create_category(session, name=name)
            QMessageBox.information(self, "تم الحفظ", "تم إنشاء التصنيف بنجاح")
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر حفظ التصنيف", str(exc))

    def add_unit(self):
        name, accepted = QInputDialog.getText(self, "وحدة جديدة", "اسم الوحدة:")
        if not accepted:
            return
        code, accepted = QInputDialog.getText(self, "رمز الوحدة", "رمز مختصر بالإنجليزية:")
        if not accepted:
            return
        try:
            with SessionLocal.begin() as session:
                create_unit(session, code=code, name=name, symbol=name)
            QMessageBox.information(self, "تم الحفظ", "تم إنشاء الوحدة بنجاح")
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر حفظ الوحدة", str(exc))
