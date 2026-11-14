"""Arabic supplier and purchase-invoice workflow."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)
from sqlalchemy.exc import SQLAlchemyError

from baynex_stationery.db.session import SessionLocal
from baynex_stationery.services.inventory import ensure_default_warehouse, list_warehouses
from baynex_stationery.services.products import list_products
from baynex_stationery.services.purchases import (
    create_purchase, create_supplier, list_purchases, list_suppliers, post_purchase,
)
from baynex_stationery.ui.components import configure_data_table, create_page_heading


class PurchasesDialog(QDialog):
    """Create and post supplier invoices; posted receipts enter the stock ledger."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("الموردون وفواتير المشتريات | BAYNEX")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(1180, 760)
        with SessionLocal.begin() as session:
            ensure_default_warehouse(session)
            self.products = list_products(session)
            self.warehouses = list_warehouses(session)
            self.suppliers = list_suppliers(session)
            self.history = list_purchases(session, limit=200)

        root = QVBoxLayout(self)
        root.addWidget(create_page_heading(
            "الموردون وفواتير المشتريات",
            "إنشاء فاتورة مورد، تسجيل الدفعة، ثم ترحيل الاستلام إلى دفتر المخزون",
            self,
        ))

        supplier_box = QGroupBox("بيانات المورد")
        supplier_form = QFormLayout(supplier_box)
        supplier_row = QHBoxLayout()
        self.supplier = QComboBox()
        self.supplier.setMinimumWidth(320)
        self.add_supplier_button = QPushButton("مورد جديد")
        supplier_row.addWidget(self.supplier, 1)
        supplier_row.addWidget(self.add_supplier_button)
        self.supplier_code = QLineEdit()
        self.supplier_invoice = QLineEdit()
        supplier_form.addRow("المورد *", supplier_row)
        supplier_form.addRow("رقم فاتورة المورد", self.supplier_invoice)
        root.addWidget(supplier_box)

        header = QGroupBox("بيانات المستند والسداد")
        form = QFormLayout(header)
        self.number = QLineEdit(f"PU-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        self.warehouse = QComboBox()
        for item in self.warehouses:
            self.warehouse.addItem(item.name, item.id)
        self.payment = QComboBox()
        for label, value in (("نقدي", "cash"), ("بطاقة", "card"), ("تحويل", "transfer")):
            self.payment.addItem(label, value)
        self.paid = QLineEdit("0.00")
        self.notes = QLineEdit()
        form.addRow("رقم فاتورة الشراء *", self.number)
        form.addRow("المستودع *", self.warehouse)
        form.addRow("طريقة السداد", self.payment)
        form.addRow("المدفوع", self.paid)
        form.addRow("ملاحظات", self.notes)
        root.addWidget(header)

        entry = QGroupBox("إضافة صنف إلى الفاتورة")
        entry_row = QHBoxLayout(entry)
        self.product = QComboBox()
        self.product.setEditable(True)
        self.product.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.product.setMinimumWidth(330)
        self.product.addItem("اختر الصنف أو ابحث بالاسم والرمز", None)
        for item in self.products:
            unit = item.unit_record.symbol if item.unit_record else item.unit
            self.product.addItem(
                f"{item.sku} | {item.name} | {unit} | تكلفة {item.cost_price:.2f}", item.id
            )
        self.quantity = QLineEdit("1")
        self.cost = QLineEdit()
        self.quantity.setMaximumWidth(90)
        self.cost.setMaximumWidth(110)
        self.add_line_button = QPushButton("إضافة للسطر")
        self.remove_line_button = QPushButton("حذف السطر")
        for widget in (
            QLabel("الصنف:"), self.product, QLabel("الكمية:"), self.quantity,
            QLabel("تكلفة الوحدة:"), self.cost, self.add_line_button, self.remove_line_button,
        ):
            entry_row.addWidget(widget)
        root.addWidget(entry)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["م", "رمز الصنف", "اسم الصنف", "الوحدة", "الكمية", "تكلفة الوحدة", "الإجمالي"]
        )
        configure_data_table(self.table, row_height=36)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setColumnWidth(0, 42)
        self.table.setColumnWidth(1, 115)
        self.table.setColumnWidth(2, 330)
        root.addWidget(self.table, 1)

        totals = QHBoxLayout()
        self.subtotal = QLabel("0.00")
        self.total = QLabel("0.00")
        self.remaining = QLabel("0.00")
        for label, value in (("الإجمالي:", self.subtotal), ("الصافي:", self.total), ("المتبقي:", self.remaining)):
            totals.addWidget(QLabel(label))
            value.setMinimumWidth(110)
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            totals.addWidget(value)
        root.addLayout(totals)

        actions = QHBoxLayout()
        self.refresh_button = QPushButton("تحديث السجل")
        self.post_button = QPushButton("حفظ وترحيل فاتورة الشراء")
        self.post_button.setObjectName("primaryAction")
        close_button = QPushButton("إغلاق")
        actions.addWidget(self.refresh_button)
        actions.addStretch(1)
        actions.addWidget(self.post_button)
        actions.addWidget(close_button)
        root.addLayout(actions)

        self.add_supplier_button.clicked.connect(self.add_supplier)
        self.product.currentIndexChanged.connect(self.fill_cost)
        self.add_line_button.clicked.connect(self.add_line)
        self.remove_line_button.clicked.connect(self.remove_line)
        self.paid.textChanged.connect(self.recalculate)
        self.post_button.clicked.connect(self.save_purchase)
        self.refresh_button.clicked.connect(self.refresh_history)
        close_button.clicked.connect(self.reject)
        self.refresh_suppliers()
        self.fill_cost()
        self.recalculate()

    @staticmethod
    def _decimal(value: str, label: str, *, positive: bool = False) -> Decimal:
        try:
            number = Decimal(value.strip())
        except (InvalidOperation, AttributeError) as exc:
            raise ValueError(f"{label} غير صالح") from exc
        if not number.is_finite() or number < 0 or (positive and number == 0):
            raise ValueError(f"{label} يجب أن يكون رقماً موجباً")
        return number

    def refresh_suppliers(self):
        selected = self.supplier.currentData()
        with SessionLocal() as session:
            self.suppliers = list_suppliers(session)
        self.supplier.clear()
        for item in self.suppliers:
            self.supplier.addItem(f"{item.code} | {item.name}", item.id)
        index = self.supplier.findData(selected)
        if index >= 0:
            self.supplier.setCurrentIndex(index)

    def add_supplier(self):
        code, ok = QInputDialog.getText(self, "مورد جديد", "رمز المورد:")
        if not ok:
            return
        name, ok = QInputDialog.getText(self, "مورد جديد", "اسم المورد:")
        if not ok:
            return
        phone, ok = QInputDialog.getText(self, "مورد جديد", "رقم الهاتف (اختياري):")
        if not ok:
            return
        try:
            with SessionLocal.begin() as session:
                create_supplier(session, code=code, name=name, phone=phone)
            self.refresh_suppliers()
            QMessageBox.information(self, "الموردون", "تم حفظ المورد")
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر حفظ المورد", str(exc))

    def fill_cost(self):
        product_id = self.product.currentData()
        product = next((item for item in self.products if item.id == product_id), None)
        if product:
            self.cost.setText(str(product.cost_price))

    def add_line(self):
        product_id = self.product.currentData()
        product = next((item for item in self.products if item.id == product_id), None)
        if product is None:
            QMessageBox.information(self, "إضافة صنف", "اختر صنفاً صحيحاً")
            return
        try:
            quantity = self._decimal(self.quantity.text(), "الكمية", positive=True)
            cost = self._decimal(self.cost.text(), "تكلفة الوحدة")
            if quantity != quantity.quantize(Decimal("0.001")):
                raise ValueError("الكمية تقبل ثلاث خانات عشرية")
            if cost != cost.quantize(Decimal("0.01")):
                raise ValueError("التكلفة تقبل خانتين عشريتين")
        except ValueError as exc:
            QMessageBox.warning(self, "بيانات الصنف", str(exc))
            return
        if any(self.table.item(row, 1).data(Qt.ItemDataRole.UserRole) == product.id for row in range(self.table.rowCount())):
            QMessageBox.information(self, "الصنف مكرر", "الصنف موجود بالفعل في الفاتورة")
            return
        unit = product.unit_record.symbol if product.unit_record else product.unit
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [str(row + 1), product.sku, product.name, unit, str(quantity), f"{cost:.2f}", f"{quantity * cost:.2f}"]
        for column, value in enumerate(values):
            cell = QTableWidgetItem(value)
            if column == 1:
                cell.setData(Qt.ItemDataRole.UserRole, product.id)
            cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, column, cell)
        self.recalculate()

    def remove_line(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            for index in range(self.table.rowCount()):
                self.table.item(index, 0).setText(str(index + 1))
            self.recalculate()

    def recalculate(self):
        subtotal = Decimal("0.00")
        for row in range(self.table.rowCount()):
            subtotal += Decimal(self.table.item(row, 4).text()) * Decimal(self.table.item(row, 5).text())
        subtotal = subtotal.quantize(Decimal("0.01"))
        try:
            paid = self._decimal(self.paid.text(), "المدفوع")
        except ValueError:
            paid = subtotal + Decimal("1")
        self.subtotal.setText(f"{subtotal:.2f}")
        self.total.setText(f"{subtotal:.2f}")
        self.remaining.setText(f"{subtotal - paid:.2f}")
        self.post_button.setEnabled(bool(self.table.rowCount()) and paid <= subtotal)

    def save_purchase(self):
        try:
            if self.supplier.currentData() is None:
                raise ValueError("أضف مورداً واختره أولاً")
            lines = []
            for row in range(self.table.rowCount()):
                lines.append({
                    "product_id": self.table.item(row, 1).data(Qt.ItemDataRole.UserRole),
                    "quantity": self.table.item(row, 4).text(),
                    "unit_cost": self.table.item(row, 5).text(),
                })
            if not lines:
                raise ValueError("أضف صنفاً واحداً على الأقل")
            with SessionLocal.begin() as session:
                purchase = create_purchase(
                    session, number=self.number.text(), supplier_id=self.supplier.currentData(),
                    warehouse_id=self.warehouse.currentData(), lines=lines,
                    paid_amount=self.paid.text(), payment_method=self.payment.currentData(),
                    supplier_invoice_number=self.supplier_invoice.text(), notes=self.notes.text(),
                )
                post_purchase(session, purchase_id=purchase.id)
                number, total = purchase.number, purchase.total
            QMessageBox.information(
                self, "تم ترحيل فاتورة الشراء",
                f"الفاتورة: {number}\nالإجمالي: {total:.2f}\n"
                "تم إدخال الكميات إلى دفتر المخزون وتسجيل الدفعة ضمن المعاملة نفسها.",
            )
            self.refresh_history()
            self.accept()
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر حفظ فاتورة الشراء", str(exc))

    def refresh_history(self):
        with SessionLocal() as session:
            self.history = list_purchases(session, limit=200)
        summary = "\n".join(
            f"{item.number} | {item.status} | {item.total:.2f}"
            for item in self.history[:12]
        )
        QMessageBox.information(
            self, "سجل فواتير المشتريات",
            summary or "لا توجد فواتير مشتريات مسجلة حتى الآن",
        )
