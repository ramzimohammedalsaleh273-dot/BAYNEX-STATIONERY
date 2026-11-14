"""Classic Arabic sales invoice entry window with live line and total calculations."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from sqlalchemy.exc import SQLAlchemyError

from baynex_stationery.db.session import SessionLocal
from baynex_stationery.services.inventory import ensure_default_warehouse, list_warehouses
from baynex_stationery.services.products import list_products
from baynex_stationery.services.customers import create_customer, list_customers
from baynex_stationery.services.sales import create_sale, post_sale
from baynex_stationery.ui.components import configure_data_table, create_page_heading


class SalesInvoiceDialog(QDialog):
    """A real invoice form: product/unit/quantity/price/discount and posted stock movement."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("فاتورة مبيعات | BAYNEX STATIONERY")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(1120, 740)
        with SessionLocal.begin() as session:
            ensure_default_warehouse(session)
            self.products = list_products(session)
            self.warehouses = list_warehouses(session)
            self.customers = list_customers(session)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(7)
        root.addWidget(create_page_heading(
            "فاتورة مبيعات",
            "إدخال الأصناف والوحدات والكميات والأسعار ثم حفظ الفاتورة وترحيلها للمخزون",
            self,
        ))

        header = QGroupBox("بيانات الفاتورة والعميل")
        form = QFormLayout(header)
        self.number = QLineEdit(f"SL-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        self.invoice_date = QDateTimeEdit(QDateTime.currentDateTime())
        self.invoice_date.setDisplayFormat("yyyy/MM/dd HH:mm")
        self.invoice_date.setCalendarPopup(True)
        self.customer = QLineEdit("عميل نقدي")
        self.phone = QLineEdit()
        self.customer_account = QComboBox()
        self.customer_account.addItem("عميل نقدي / بدون حساب", None)
        for customer_record in self.customers:
            self.customer_account.addItem(
                f"{customer_record.code} | {customer_record.name}", customer_record.id
            )
        self.add_customer_button = QPushButton("عميل جديد")
        customer_row = QHBoxLayout()
        customer_row.addWidget(self.customer_account, 1)
        customer_row.addWidget(self.add_customer_button)
        self.warehouse = QComboBox()
        for warehouse in self.warehouses:
            self.warehouse.addItem(warehouse.name, warehouse.id)
        self.payment = QComboBox()
        for label, value in (("نقدي", "cash"), ("شبكة / بطاقة", "card"), ("تحويل", "transfer"), ("آجل", "credit")):
            self.payment.addItem(label, value)
        self.paid = QLineEdit("0.00")
        self.invoice_discount = QLineEdit("0.00")
        form.addRow("رقم الفاتورة:", self.number)
        form.addRow("تاريخ الفاتورة:", self.invoice_date)
        form.addRow("حساب العميل:", customer_row)
        form.addRow("اسم العميل:", self.customer)
        form.addRow("رقم الهاتف:", self.phone)
        form.addRow("المستودع:", self.warehouse)
        form.addRow("طريقة السداد:", self.payment)
        form.addRow("المدفوع:", self.paid)
        form.addRow("خصم الفاتورة:", self.invoice_discount)
        root.addWidget(header)

        entry = QGroupBox("إضافة صنف إلى تفاصيل الفاتورة")
        entry_layout = QHBoxLayout(entry)
        self.product = QComboBox()
        self.product.setMinimumWidth(350)
        self.product.setEditable(True)
        self.product.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.product.addItem("اختر الصنف أو ابحث بالاسم / الرمز / الباركود", None)
        for product in self.products:
            unit = product.unit_record.symbol if product.unit_record else product.unit
            self.product.addItem(f"{product.sku} | {product.name} | {unit} | {product.sale_price:.2f}", product.id)
        self.quantity = QLineEdit("1")
        self.price = QLineEdit()
        self.line_discount = QLineEdit("0.00")
        self.quantity.setMaximumWidth(90)
        self.price.setMaximumWidth(110)
        self.line_discount.setMaximumWidth(100)
        add_line = QPushButton("إضافة للسطر")
        add_line.setObjectName("primaryAction")
        remove_line = QPushButton("حذف السطر المحدد")
        entry_layout.addWidget(QLabel("الصنف:"))
        entry_layout.addWidget(self.product, 1)
        entry_layout.addWidget(QLabel("الكمية:"))
        entry_layout.addWidget(self.quantity)
        entry_layout.addWidget(QLabel("السعر:"))
        entry_layout.addWidget(self.price)
        entry_layout.addWidget(QLabel("الخصم:"))
        entry_layout.addWidget(self.line_discount)
        entry_layout.addWidget(add_line)
        entry_layout.addWidget(remove_line)
        root.addWidget(entry)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "م", "رمز الصنف", "اسم الصنف", "الوحدة", "الكمية", "سعر الوحدة", "الخصم", "الإجمالي"
        ])
        configure_data_table(self.table, row_height=34)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setColumnWidth(0, 42)
        self.table.setColumnWidth(1, 105)
        self.table.setColumnWidth(2, 300)
        self.table.setColumnWidth(3, 85)
        self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 115)
        self.table.setColumnWidth(6, 95)
        root.addWidget(self.table, 1)

        totals = QGroupBox("ملخص الفاتورة")
        totals_layout = QHBoxLayout(totals)
        self.subtotal_label = QLabel("0.00")
        self.discount_label = QLabel("0.00")
        self.total_label = QLabel("0.00")
        self.remaining_label = QLabel("0.00")
        for label, widget in (
            ("الإجمالي قبل الخصم:", self.subtotal_label),
            ("الخصومات:", self.discount_label),
            ("الصافي:", self.total_label),
            ("المتبقي:", self.remaining_label),
        ):
            widget.setMinimumWidth(95)
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            totals_layout.addWidget(QLabel(label))
            totals_layout.addWidget(widget)
        root.addWidget(totals)

        actions = QHBoxLayout()
        self.save_button = QPushButton("حفظ وترحيل الفاتورة")
        self.save_button.setObjectName("primaryAction")
        self.cancel_button = QPushButton("إغلاق")
        actions.addStretch(1)
        actions.addWidget(self.save_button)
        actions.addWidget(self.cancel_button)
        root.addLayout(actions)

        add_line.clicked.connect(self.add_line)
        remove_line.clicked.connect(self.remove_line)
        self.save_button.clicked.connect(self.save_invoice)
        self.add_customer_button.clicked.connect(self.add_customer)
        self.customer_account.currentIndexChanged.connect(self.select_customer)
        self.cancel_button.clicked.connect(self.reject)
        self.invoice_discount.textChanged.connect(self.recalculate)
        self.paid.textChanged.connect(self.recalculate)
        self.table.itemChanged.connect(self.recalculate)
        self.product.currentIndexChanged.connect(self._fill_price)
        self._fill_price()

    def refresh_customers(self, selected_id=None):
        with SessionLocal() as session:
            self.customers = list_customers(session)
        self.customer_account.blockSignals(True)
        self.customer_account.clear()
        self.customer_account.addItem("عميل نقدي / بدون حساب", None)
        for customer_record in self.customers:
            self.customer_account.addItem(
                f"{customer_record.code} | {customer_record.name}", customer_record.id
            )
        index = self.customer_account.findData(selected_id)
        if index >= 0:
            self.customer_account.setCurrentIndex(index)
        self.customer_account.blockSignals(False)
        self.select_customer()

    def select_customer(self):
        customer_id = self.customer_account.currentData()
        customer_record = next(
            (item for item in self.customers if item.id == customer_id), None
        )
        if customer_record is not None:
            self.customer.setText(customer_record.name)
            self.phone.setText(customer_record.phone or "")
        else:
            self.customer.setText("عميل نقدي")
            self.phone.clear()

    def add_customer(self):
        code, ok = QInputDialog.getText(self, "عميل جديد", "رمز العميل:")
        if not ok:
            return
        name, ok = QInputDialog.getText(self, "عميل جديد", "اسم العميل:")
        if not ok:
            return
        phone, ok = QInputDialog.getText(self, "عميل جديد", "رقم الهاتف (اختياري):")
        if not ok:
            return
        try:
            with SessionLocal.begin() as session:
                customer_record = create_customer(
                    session, code=code, name=name, phone=phone
                )
                customer_id = customer_record.id
            self.refresh_customers(customer_id)
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر حفظ العميل", str(exc))

    def _fill_price(self):
        product_id = self.product.currentData()
        product = next((item for item in self.products if item.id == product_id), None)
        if product is not None:
            self.price.setText(str(product.sale_price))

    @staticmethod
    def _number(value: str, label: str, *, allow_zero: bool = True) -> Decimal:
        try:
            result = Decimal(value.strip())
        except (InvalidOperation, AttributeError) as exc:
            raise ValueError(f"{label} غير صالح") from exc
        if not result.is_finite() or result < 0 or (not allow_zero and result == 0):
            raise ValueError(f"{label} يجب أن يكون رقماً موجباً أو صفراً")
        return result

    def add_line(self):
        product_id = self.product.currentData()
        product = next((item for item in self.products if item.id == product_id), None)
        if product is None:
            QMessageBox.information(self, "إضافة صنف", "اختر صنفاً صحيحاً من القائمة")
            return
        try:
            quantity = self._number(self.quantity.text(), "الكمية", allow_zero=False)
            price = self._number(self.price.text(), "سعر الوحدة")
            discount = self._number(self.line_discount.text(), "الخصم")
            if quantity != quantity.quantize(Decimal("0.001")):
                raise ValueError("الكمية تقبل حتى ثلاث خانات عشرية")
            if price != price.quantize(Decimal("0.01")) or discount != discount.quantize(Decimal("0.01")):
                raise ValueError("السعر والخصم يقبلان خانتين عشريتين")
            gross = (quantity * price).quantize(Decimal("0.01"))
            if discount > gross:
                raise ValueError("الخصم أكبر من قيمة السطر")
        except ValueError as exc:
            QMessageBox.warning(self, "بيانات السطر", str(exc))
            return
        for row in range(self.table.rowCount()):
            if self.table.item(row, 1).data(Qt.ItemDataRole.UserRole) == product.id:
                QMessageBox.information(self, "الصنف مكرر", "الصنف موجود بالفعل؛ احذف السطر القديم أو عدّله")
                return
        unit = product.unit_record.symbol if product.unit_record else product.unit
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [str(row + 1), product.sku, product.name, unit, str(quantity), f"{price:.2f}", f"{discount:.2f}", f"{gross - discount:.2f}"]
        for column, value in enumerate(values):
            cell = QTableWidgetItem(value)
            if column == 1:
                cell.setData(Qt.ItemDataRole.UserRole, product.id)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
            elif column in (0, 2, 3, 7):
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

    def _line_values(self):
        result = []
        for row in range(self.table.rowCount()):
            product_id = self.table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            quantity = self._number(self.table.item(row, 4).text(), f"كمية السطر {row + 1}", allow_zero=False)
            price = self._number(self.table.item(row, 5).text(), f"سعر السطر {row + 1}")
            discount = self._number(self.table.item(row, 6).text(), f"خصم السطر {row + 1}")
            if quantity != quantity.quantize(Decimal("0.001")):
                raise ValueError(f"الكمية في السطر {row + 1} تتجاوز ثلاث خانات عشرية")
            if price != price.quantize(Decimal("0.01")) or discount != discount.quantize(Decimal("0.01")):
                raise ValueError(f"السعر والخصم في السطر {row + 1} يقبلان خانتين عشريتين")
            result.append({"product_id": product_id, "quantity": quantity, "unit_price": price, "discount": discount})
        return result

    def recalculate(self):
        if not hasattr(self, "table"):
            return
        try:
            subtotal = Decimal("0.00")
            line_discounts = Decimal("0.00")
            for row in range(self.table.rowCount()):
                quantity = self._number(self.table.item(row, 4).text(), "الكمية", allow_zero=False)
                price = self._number(self.table.item(row, 5).text(), "السعر")
                discount = self._number(self.table.item(row, 6).text(), "الخصم")
                gross = (quantity * price).quantize(Decimal("0.01"))
                if discount > gross:
                    raise ValueError("خصم أحد الأسطر أكبر من إجماليه")
                subtotal += gross
                line_discounts += discount
                self.table.blockSignals(True)
                self.table.item(row, 7).setText(f"{gross - discount:.2f}")
                self.table.blockSignals(False)
            invoice_discount = self._number(self.invoice_discount.text(), "خصم الفاتورة")
            if invoice_discount > subtotal - line_discounts:
                raise ValueError("خصم الفاتورة أكبر من صافي تفاصيل الأصناف")
            total = subtotal - line_discounts - invoice_discount
            paid = self._number(self.paid.text(), "المدفوع")
            self.subtotal_label.setText(f"{subtotal:.2f}")
            self.discount_label.setText(f"{line_discounts + invoice_discount:.2f}")
            self.total_label.setText(f"{total:.2f}")
            self.remaining_label.setText(f"{total - paid:.2f}")
            self.save_button.setEnabled(bool(self.table.rowCount()) and paid <= total)
        except (ValueError, AttributeError):
            self.save_button.setEnabled(False)

    def save_invoice(self):
        try:
            lines = self._line_values()
            if not lines:
                raise ValueError("أضف صنفاً واحداً على الأقل")
            with SessionLocal.begin() as session:
                sale = create_sale(
                    session,
                    number=self.number.text(),
                    warehouse_id=self.warehouse.currentData(),
                    lines=lines,
                    customer_name=self.customer.text(),
                    customer_phone=self.phone.text(),
                    customer_id=self.customer_account.currentData(),
                    payment_method=self.payment.currentData(),
                    paid_amount=self.paid.text(),
                    discount=self.invoice_discount.text(),
                    invoice_date=self.invoice_date.dateTime().toPython(),
                )
                post_sale(session, sale_id=sale.id)
                number = sale.number
                total = sale.total
            QMessageBox.information(
                self, "تم ترحيل الفاتورة",
                f"تم حفظ وترحيل الفاتورة رقم {number}\nالإجمالي: {total:.2f}\n"
                "تم تسجيل حركة المخزون والمدفوعات ضمن معاملة واحدة.",
            )
            self.accept()
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر حفظ فاتورة المبيعات", str(exc))
