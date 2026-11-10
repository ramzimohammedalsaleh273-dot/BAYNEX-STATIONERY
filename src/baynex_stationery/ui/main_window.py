"""Arabic RTL product catalog screen with searchable product maintenance."""
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
from baynex_stationery.services.products import (
    create_product, list_products, set_product_active, update_product,
)


class ProductDialog(QDialog):
    def __init__(self, categories, units, parent=None, product=None):
        super().__init__(parent)
        self.product = product
        self.setWindowTitle("تعديل صنف" if product else "إضافة صنف")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.fields = {
            "sku": QLineEdit(product.sku if product else ""),
            "name": QLineEdit(product.name if product else ""),
            "barcode": QLineEdit(product.barcode or "" if product else ""),
            "sale": QLineEdit(str(product.sale_price) if product else "0.00"),
            "cost": QLineEdit(str(product.cost_price) if product else "0.00"),
            "stock": QLineEdit(str(product.stock_quantity) if product else "0"),
            "minimum": QLineEdit(str(product.minimum_stock) if product else "0"),
            "notes": QLineEdit(product.notes or "" if product else ""),
        }
        self.category = QComboBox()
        self.category.addItem("بدون تصنيف", None)
        for item in categories:
            self.category.addItem(item.name, item.id)
        self.unit = QComboBox()
        self.unit.addItem("الوحدة الافتراضية (قطعة)", None)
        for item in units:
            self.unit.addItem(f"{item.name} ({item.symbol})", item.id)
        if product:
            self._select_data(self.category, product.category_id)
            self._select_data(self.unit, product.unit_id)
        form = QFormLayout()
        for key, label in [
            ("sku", "رمز الصنف *"), ("name", "اسم الصنف *"),
            ("barcode", "الباركود"), ("sale", "سعر البيع"),
            ("cost", "سعر التكلفة"), ("stock", "الرصيد الافتتاحي"),
            ("minimum", "حد إعادة الطلب"), ("notes", "ملاحظات"),
        ]:
            if key == "stock" and product:
                continue
            form.addRow(label, self.fields[key])
        form.addRow("التصنيف", self.category)
        form.addRow("وحدة القياس", self.unit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @staticmethod
    def _select_data(combo, value):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def values(self):
        try:
            values = {
                "sku": self.fields["sku"].text(),
                "name": self.fields["name"].text(),
                "sale_price": Decimal(self.fields["sale"].text().strip() or "0"),
                "cost_price": Decimal(self.fields["cost"].text().strip() or "0"),
                "barcode": self.fields["barcode"].text(),
                "minimum_stock": Decimal(self.fields["minimum"].text().strip() or "0"),
                "category_id": self.category.currentData(),
                "unit_id": self.unit.currentData(),
                "notes": self.fields["notes"].text(),
            }
            if not self.product:
                values["opening_stock"] = Decimal(self.fields["stock"].text().strip() or "0")
                values["unit"] = "قطعة"
            return values
        except InvalidOperation as exc:
            raise ValueError("أدخل أرقاماً صحيحة في حقول الأسعار والكميات") from exc


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BAYNEX STATIONERY | نظام القرطاسية")
        self.resize(1280, 800)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QWidget()
        layout = QVBoxLayout(root)
        header = QLabel("BAYNEX STATIONERY")
        header.setStyleSheet("font-size: 24px; font-weight: 700; padding: 12px;")
        subtitle = QLabel("إدارة الأصناف والتصنيفات ووحدات القياس والباركود")
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("ابحث بالاسم أو الرمز أو الباركود...")
        self.add_button = QPushButton("إضافة صنف")
        self.edit_button = QPushButton("تعديل المحدد")
        self.deactivate_button = QPushButton("إيقاف الصنف")
        self.category_button = QPushButton("إضافة تصنيف")
        self.unit_button = QPushButton("إضافة وحدة")
        self.refresh_button = QPushButton("تحديث")
        for widget in (self.add_button, self.edit_button, self.deactivate_button,
                       self.category_button, self.unit_button, self.refresh_button):
            toolbar.addWidget(widget)
        toolbar.addWidget(self.search, 1)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["الرمز", "الباركود", "اسم الصنف", "التصنيف", "الوحدة", "سعر التكلفة", "سعر البيع", "الرصيد"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(header)
        layout.addWidget(subtitle)
        layout.addLayout(toolbar)
        layout.addWidget(self.table)
        self.setCentralWidget(root)

        self.add_button.clicked.connect(self.add_product)
        self.edit_button.clicked.connect(self.edit_product)
        self.deactivate_button.clicked.connect(self.deactivate_product)
        self.category_button.clicked.connect(self.add_category)
        self.unit_button.clicked.connect(self.add_unit)
        self.refresh_button.clicked.connect(self.refresh_products)
        self.search.textChanged.connect(self.refresh_products)
        self.table.doubleClicked.connect(self.edit_product)
        self.refresh_products()

    def _catalog(self):
        with SessionLocal() as session:
            return list_categories(session), list_units(session)

    def refresh_products(self):
        with SessionLocal() as session:
            products = list_products(session, search=self.search.text())
            self.table.setRowCount(len(products))
            for row, product in enumerate(products):
                values = [
                    product.sku, product.barcode or "", product.name,
                    product.category.name if product.category else "—",
                    product.unit_record.symbol if product.unit_record else product.unit,
                    f"{product.cost_price:.2f}", f"{product.sale_price:.2f}",
                    f"{product.stock_quantity:g}",
                ]
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(str(value))
                    if column == 0:
                        cell.setData(Qt.ItemDataRole.UserRole, product.id)
                    self.table.setItem(row, column, cell)

    def _selected_product_id(self):
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, 0) is None:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def add_product(self):
        categories, units = self._catalog()
        dialog = ProductDialog(categories, units, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with SessionLocal.begin() as session:
                create_product(session, **dialog.values())
            self.refresh_products()
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر حفظ الصنف", str(exc))

    def edit_product(self):
        product_id = self._selected_product_id()
        if product_id is None:
            QMessageBox.information(self, "تعديل صنف", "حدد صنفاً أولاً")
            return
        categories, units = self._catalog()
        with SessionLocal() as session:
            from baynex_stationery.db.models import Product
            product = session.get(Product, product_id)
            if product is None:
                QMessageBox.warning(self, "تعديل صنف", "الصنف غير موجود")
                return
            dialog = ProductDialog(categories, units, self, product)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            values = dialog.values()
        try:
            with SessionLocal.begin() as session:
                update_product(session, product_id, **values)
            self.refresh_products()
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر تعديل الصنف", str(exc))

    def deactivate_product(self):
        product_id = self._selected_product_id()
        if product_id is None:
            QMessageBox.information(self, "إيقاف صنف", "حدد صنفاً أولاً")
            return
        answer = QMessageBox.question(
            self, "تأكيد الإيقاف", "سيتم إيقاف الصنف دون حذف سجله. هل تريد المتابعة؟"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            with SessionLocal.begin() as session:
                set_product_active(session, product_id, False)
            self.refresh_products()
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر إيقاف الصنف", str(exc))

    def add_category(self):
        name, accepted = QInputDialog.getText(self, "إضافة تصنيف", "اسم التصنيف:")
        if not accepted:
            return
        try:
            with SessionLocal.begin() as session:
                create_category(session, name)
            QMessageBox.information(self, "التصنيفات", "تم حفظ التصنيف")
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر حفظ التصنيف", str(exc))

    def add_unit(self):
        name, accepted = QInputDialog.getText(self, "إضافة وحدة", "اسم الوحدة:")
        if not accepted:
            return
        symbol, accepted = QInputDialog.getText(self, "إضافة وحدة", "رمز الوحدة:")
        if not accepted:
            return
        try:
            with SessionLocal.begin() as session:
                create_unit(session, name, symbol)
            QMessageBox.information(self, "وحدات القياس", "تم حفظ الوحدة")
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر حفظ الوحدة", str(exc))
