"""Independent Arabic cashier screen for BAYNEX STATIONERY."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)
from sqlalchemy.exc import SQLAlchemyError

from baynex_stationery.db.session import SessionLocal
from baynex_stationery.services.inventory import ensure_default_warehouse, list_warehouses
from baynex_stationery.services.pos import calculate_line, calculate_totals, decimal_input
from baynex_stationery.services.products import get_product_by_barcode, list_products
from baynex_stationery.services.sales import create_sale, post_sale
from baynex_stationery.ui.components import configure_data_table, create_page_heading


class POSPaymentDialog(QDialog):
    """Confirm tender and calculate cash change before posting."""

    def __init__(self, total: Decimal, parent=None):
        super().__init__(parent)
        self.setWindowTitle("الدفع وإنهاء البيع")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.total = total
        self.method = QComboBox()
        for label, value in (("نقدي", "cash"), ("شبكة / بطاقة", "card"),
                             ("تحويل", "transfer"), ("آجل", "credit")):
            self.method.addItem(label, value)
        self.received = QLineEdit(f"{total:.2f}")
        self.due = QLabel(f"{total:.2f}")
        self.change = QLabel("0.00")
        form = QFormLayout()
        form.addRow("المبلغ المستحق:", self.due)
        form.addRow("طريقة الدفع:", self.method)
        form.addRow("المبلغ المستلم:", self.received)
        form.addRow("الباقي للعميل:", self.change)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("تأكيد الدفع")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("إلغاء")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(create_page_heading("إنهاء عملية البيع", "راجع المبلغ وطريقة السداد قبل ترحيل الفاتورة", self))
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.received.textChanged.connect(self._update_change)
        self.method.currentIndexChanged.connect(self._method_changed)
        self._method_changed()

    def _method_changed(self):
        is_credit = self.method.currentData() == "credit"
        self.received.setEnabled(not is_credit)
        if is_credit:
            self.received.setText("0.00")
        elif Decimal(self.received.text() or "0") == 0:
            self.received.setText(f"{self.total:.2f}")
        self._update_change()

    def _update_change(self):
        try:
            amount = decimal_input(self.received.text() or "0", "المبلغ المستلم")
            self.change.setText(f"{max(Decimal('0'), amount - self.total):.2f}")
        except ValueError:
            self.change.setText("—")

    def _validate(self):
        try:
            amount = Decimal("0.00") if self.method.currentData() == "credit" else decimal_input(
                self.received.text(), "المبلغ المستلم"
            )
            if self.method.currentData() != "credit" and amount < self.total:
                raise ValueError("المبلغ المستلم أقل من المبلغ المستحق")
            self.paid_amount = self.total if self.method.currentData() != "credit" else Decimal("0.00")
            self.payment_method = self.method.currentData()
            self.change_amount = max(Decimal("0.00"), amount - self.total)
            self.accept()
        except ValueError as exc:
            QMessageBox.warning(self, "بيانات الدفع", str(exc))


class POSDialog(QDialog):
    """Fast barcode-first cashier with held tickets and transactional sale posting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BAYNEX STATIONERY | نقطة البيع")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(1360, 820)
        self.cart: dict[int, dict] = {}
        self.held_tickets: list[dict] = []
        with SessionLocal.begin() as session:
            ensure_default_warehouse(session)
            self.products = list_products(session)
            self.warehouses = list_warehouses(session)
        self.product_by_id = {p.id: p for p in self.products}

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(7)
        root.addWidget(create_page_heading(
            "نقطة البيع POS",
            "واجهة كاشير مستقلة — مسح الباركود، إدارة السلة، الدفع وترحيل المخزون",
            self,
        ))

        top = QHBoxLayout()
        self.invoice_no = QLabel(f"POS-{datetime.now():%Y%m%d-%H%M%S}")
        self.clock = QLabel(datetime.now().strftime("%Y/%m/%d %H:%M"))
        self.warehouse = QComboBox()
        for warehouse in self.warehouses:
            self.warehouse.addItem(warehouse.name, warehouse.id)
        top.addWidget(QLabel("رقم العملية:"))
        top.addWidget(self.invoice_no)
        top.addStretch(1)
        top.addWidget(QLabel("المستودع:"))
        top.addWidget(self.warehouse)
        top.addWidget(self.clock)
        root.addLayout(top)

        self.barcode = QLineEdit()
        self.barcode.setPlaceholderText("امسح الباركود هنا أو اكتب رمز الصنف ثم اضغط Enter...")
        self.barcode.setMinimumHeight(42)
        self.barcode.setObjectName("posBarcode")
        self.search = QLineEdit()
        self.search.setPlaceholderText("بحث بالاسم أو الرمز أو الباركود...")
        self.search.setMinimumHeight(36)
        lookup = QVBoxLayout()
        lookup.addWidget(self.barcode)
        lookup.addWidget(self.search)

        self.results = QTableWidget(0, 4)
        self.results.setHorizontalHeaderLabels(["الرمز", "الباركود", "اسم الصنف", "سعر البيع"])
        configure_data_table(self.results, row_height=34)
        self.results.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.results.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results.setColumnWidth(0, 100)
        self.results.setColumnWidth(1, 125)
        self.results.setColumnWidth(2, 230)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.addLayout(lookup)
        left_layout.addWidget(QLabel("الأصناف المتاحة — انقر مرتين لإضافتها"))
        left_layout.addWidget(self.results, 1)

        self.cart_table = QTableWidget(0, 8)
        self.cart_table.setHorizontalHeaderLabels(
            ["م", "رمز الصنف", "اسم الصنف", "الوحدة", "الكمية", "السعر", "الخصم", "الإجمالي"]
        )
        configure_data_table(self.cart_table, row_height=38)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cart_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.cart_table.setColumnWidth(0, 38)
        self.cart_table.setColumnWidth(1, 90)
        self.cart_table.setColumnWidth(2, 205)
        self.cart_table.setColumnWidth(3, 65)
        self.cart_table.setColumnWidth(4, 75)
        self.cart_table.setColumnWidth(5, 85)
        self.cart_table.setColumnWidth(6, 75)
        self.cart_table.setColumnWidth(7, 95)
        self.cart_table.itemChanged.connect(self._cart_edited)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.cart_table)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        splitter.setSizes([470, 780])
        root.addWidget(splitter, 1)

        totals_box = QGroupBox("إجماليات الفاتورة")
        totals = QHBoxLayout(totals_box)
        self.subtotal_label = QLabel("0.00")
        self.discount_label = QLabel("0.00")
        self.total_label = QLabel("0.00")
        self.total_label.setObjectName("posGrandTotal")
        self.received_preview = QLabel("0.00")
        self.change_preview = QLabel("0.00")
        for caption, widget in (
            ("قبل الخصم:", self.subtotal_label), ("الخصم:", self.discount_label),
            ("الصافي:", self.total_label), ("المستلم المتوقع:", self.received_preview),
            ("الباقي:", self.change_preview),
        ):
            widget.setMinimumWidth(90)
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            totals.addWidget(QLabel(caption))
            totals.addWidget(widget)
        root.addWidget(totals_box)

        actions = QHBoxLayout()
        self.customer = QLineEdit("عميل نقدي")
        self.customer.setMaximumWidth(180)
        self.remove_button = QPushButton("حذف الصنف")
        self.qty_button = QPushButton("تعديل الكمية")
        self.hold_button = QPushButton("تعليق F4")
        self.restore_button = QPushButton("استرجاع F6")
        self.clear_button = QPushButton("فاتورة جديدة")
        self.pay_button = QPushButton("الدفع وإنهاء البيع F8")
        self.pay_button.setObjectName("primaryAction")
        self.print_button = QPushButton("طباعة آخر إيصال F9")
        actions.addWidget(QLabel("العميل:"))
        actions.addWidget(self.customer)
        actions.addWidget(self.remove_button)
        actions.addWidget(self.qty_button)
        actions.addWidget(self.hold_button)
        actions.addWidget(self.restore_button)
        actions.addWidget(self.clear_button)
        actions.addStretch(1)
        actions.addWidget(self.print_button)
        actions.addWidget(self.pay_button)
        root.addLayout(actions)

        self.remove_button.clicked.connect(self.remove_selected)
        self.qty_button.clicked.connect(self.edit_quantity)
        self.hold_button.clicked.connect(self.hold_ticket)
        self.restore_button.clicked.connect(self.restore_ticket)
        self.clear_button.clicked.connect(self.new_ticket)
        self.pay_button.clicked.connect(self.checkout)
        self.print_button.clicked.connect(self.print_receipt)
        self.barcode.returnPressed.connect(self.scan_barcode)
        self.search.textChanged.connect(self.refresh_results)
        self.results.cellDoubleClicked.connect(self._result_double_clicked)
        self.refresh_results()
        self.barcode.setFocus()

        for sequence, callback in (
            ("F2", lambda: self.search.setFocus()),
            ("F4", self.hold_ticket),
            ("F6", self.restore_ticket),
            ("F8", self.checkout),
            ("F9", self.print_receipt),
            ("Delete", self.remove_selected),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)

    def refresh_results(self):
        term = self.search.text().strip().casefold()
        products = [p for p in self.products if not term or term in p.name.casefold()
                    or term in p.sku.casefold() or term in (p.barcode or "").casefold()]
        self.results.setRowCount(len(products))
        for row, product in enumerate(products):
            values = [product.sku, product.barcode or "—", product.name, f"{product.sale_price:.2f}"]
            for col, value in enumerate(values):
                self.results.setItem(row, col, QTableWidgetItem(str(value)))
            self.results.item(row, 0).setData(Qt.ItemDataRole.UserRole, product.id)

    def scan_barcode(self):
        code = self.barcode.text().strip()
        if not code:
            return
        product = next((p for p in self.products if p.barcode == code or p.sku == code), None)
        if product is None:
            QMessageBox.information(self, "الصنف غير موجود", f"لم يتم العثور على صنف بالرمز: {code}")
            self.barcode.selectAll()
            return
        self.add_product(product.id)
        self.barcode.clear()
        self.barcode.setFocus()

    def _result_double_clicked(self, row, _column):
        item = self.results.item(row, 0)
        if item:
            self.add_product(item.data(Qt.ItemDataRole.UserRole))

    def add_product(self, product_id: int):
        product = self.product_by_id.get(product_id)
        if product is None:
            return
        if product_id in self.cart:
            self.cart[product_id]["quantity"] += Decimal("1.000")
        else:
            self.cart[product_id] = {
                "product": product, "quantity": Decimal("1.000"),
                "unit_price": product.sale_price, "discount": Decimal("0.00"),
            }
        self.render_cart()

    def render_cart(self):
        self.cart_table.blockSignals(True)
        self.cart_table.setRowCount(len(self.cart))
        for row, (product_id, line) in enumerate(self.cart.items()):
            p = line["product"]
            unit = p.unit_record.symbol if p.unit_record else p.unit
            calc = calculate_line(line["quantity"], line["unit_price"], line["discount"])
            values = [str(row + 1), p.sku, p.name, unit, f'{line["quantity"]:.3f}',
                      f'{line["unit_price"]:.2f}', f'{line["discount"]:.2f}', f'{calc["total"]:.2f}']
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if col in (0, 1, 2, 3, 7):
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 1:
                    cell.setData(Qt.ItemDataRole.UserRole, product_id)
                self.cart_table.setItem(row, col, cell)
        self.cart_table.blockSignals(False)
        self.recalculate()

    def _cart_edited(self, item):
        row = item.row()
        if item.column() not in (4, 5, 6) or row < 0:
            return
        key_item = self.cart_table.item(row, 1)
        product_id = key_item.data(Qt.ItemDataRole.UserRole) if key_item else None
        if product_id not in self.cart:
            return
        try:
            line = self.cart[product_id]
            calc = calculate_line(
                self.cart_table.item(row, 4).text(),
                self.cart_table.item(row, 5).text(),
                self.cart_table.item(row, 6).text(),
            )
            line.update({k: calc[k] for k in ("quantity", "unit_price", "discount")})
            self.render_cart()
        except (ValueError, AttributeError):
            QMessageBox.warning(self, "تفاصيل الصنف", "تحقق من الكمية والسعر والخصم ثم أعد الإدخال.")
            self.render_cart()

    def recalculate(self):
        lines = [calculate_line(x["quantity"], x["unit_price"], x["discount"])
                 for x in self.cart.values()]
        totals = calculate_totals(lines)
        self.subtotal_label.setText(f'{totals["subtotal"]:.2f}')
        self.discount_label.setText(f'{totals["discount"]:.2f}')
        self.total_label.setText(f'{totals["total"]:.2f}')
        self.received_preview.setText(f'{totals["total"]:.2f}')
        self.change_preview.setText("0.00")

    def remove_selected(self):
        row = self.cart_table.currentRow()
        if row < 0:
            return
        key_item = self.cart_table.item(row, 1)
        if key_item:
            self.cart.pop(key_item.data(Qt.ItemDataRole.UserRole), None)
        self.render_cart()

    def edit_quantity(self):
        row = self.cart_table.currentRow()
        if row < 0:
            return
        item = self.cart_table.item(row, 4)
        self.cart_table.editItem(item)

    def new_ticket(self):
        if self.cart and QMessageBox.question(self, "فاتورة جديدة", "هل تريد تفريغ الفاتورة الحالية؟") != QMessageBox.StandardButton.Yes:
            return
        self.cart.clear()
        self.customer.setText("عميل نقدي")
        self.render_cart()
        self.invoice_no.setText(f"POS-{datetime.now():%Y%m%d-%H%M%S}")

    def hold_ticket(self):
        if not self.cart:
            QMessageBox.information(self, "تعليق الفاتورة", "لا توجد أصناف لتعليقها.")
            return
        self.held_tickets.append({
            "cart": {k: dict(v) for k, v in self.cart.items()},
            "customer": self.customer.text(),
            "warehouse_id": self.warehouse.currentData(),
            "number": self.invoice_no.text(),
        })
        self.cart.clear()
        self.customer.setText("عميل نقدي")
        self.invoice_no.setText(f"POS-{datetime.now():%Y%m%d-%H%M%S}")
        self.render_cart()
        QMessageBox.information(self, "تعليق الفاتورة", f"تم تعليق الفاتورة. عدد الفواتير المعلقة: {len(self.held_tickets)}")

    def restore_ticket(self):
        if not self.held_tickets:
            QMessageBox.information(self, "استرجاع الفاتورة", "لا توجد فواتير معلقة في جلسة الكاشير الحالية.")
            return
        if self.cart and QMessageBox.question(self, "استرجاع", "سيتم تعليق السلة الحالية تلقائياً. متابعة؟") != QMessageBox.StandardButton.Yes:
            return
        if self.cart:
            self.held_tickets.append({"cart": self.cart, "customer": self.customer.text(),
                                      "warehouse_id": self.warehouse.currentData(), "number": self.invoice_no.text()})
        ticket = self.held_tickets.pop()
        self.cart = ticket["cart"]
        self.customer.setText(ticket["customer"])
        self.invoice_no.setText(ticket["number"])
        index = self.warehouse.findData(ticket["warehouse_id"])
        if index >= 0:
            self.warehouse.setCurrentIndex(index)
        self.render_cart()

    def checkout(self):
        if not self.cart:
            QMessageBox.information(self, "الدفع", "أضف صنفاً واحداً على الأقل.")
            return
        totals = calculate_totals([
            calculate_line(x["quantity"], x["unit_price"], x["discount"])
            for x in self.cart.values()
        ])
        payment = POSPaymentDialog(totals["total"], self)
        if payment.exec() != QDialog.DialogCode.Accepted:
            return
        lines = [{
            "product_id": product_id, "quantity": item["quantity"],
            "unit_price": item["unit_price"], "discount": item["discount"],
        } for product_id, item in self.cart.items()]
        try:
            with SessionLocal.begin() as session:
                sale = create_sale(
                    session, number=self.invoice_no.text(),
                    warehouse_id=self.warehouse.currentData(), lines=lines,
                    customer_name=self.customer.text().strip() or "عميل نقدي",
                    payment_method=payment.payment_method,
                    paid_amount=payment.paid_amount,
                )
                post_sale(session, sale_id=sale.id)
                self.last_receipt = {
                    "number": sale.number, "customer": sale.customer_name,
                    "date": sale.invoice_date.strftime("%Y-%m-%d %H:%M"),
                    "lines": [(i.product_name, i.quantity, i.unit_price, i.line_total) for i in sale.items],
                    "total": sale.total, "paid": sale.paid_amount,
                    "change": payment.change_amount,
                }
            QMessageBox.information(
                self, "تم البيع بنجاح",
                f"الفاتورة: {self.last_receipt['number']}\n"
                f"الإجمالي: {totals['total']:.2f}\n"
                f"الباقي للعميل: {payment.change_amount:.2f}\n"
                "تم تسجيل البيع وخصم المخزون وتسجيل التحصيل ضمن معاملة واحدة.",
            )
            self.cart.clear()
            self.customer.setText("عميل نقدي")
            self.invoice_no.setText(f"POS-{datetime.now():%Y%m%d-%H%M%S}")
            self.render_cart()
            self.barcode.setFocus()
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر إتمام البيع", str(exc))

    def print_receipt(self):
        receipt = getattr(self, "last_receipt", None)
        if not receipt:
            QMessageBox.information(self, "طباعة الإيصال", "لا توجد فاتورة مكتملة للطباعة في هذه الجلسة.")
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("طباعة إيصال البيع")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        rows = "".join(
            f"<tr><td>{escape(str(name))}</td><td>{qty}</td><td>{price:.2f}</td><td>{total:.2f}</td></tr>"
            for name, qty, price, total in receipt["lines"]
        )
        html = (
            "<html><meta charset='utf-8'><body dir='rtl' style='font-family:Arial'>"
            "<h2>BAYNEX STATIONERY</h2><h3>إيصال بيع</h3>"
            f"<p>رقم الفاتورة: {escape(receipt['number'])}</p>"
            f"<p>العميل: {escape(receipt['customer'])}</p><p>التاريخ: {receipt['date']}</p>"
            "<table border='1' cellspacing='0' cellpadding='5' width='100%'>"
            "<tr><th>الصنف</th><th>الكمية</th><th>السعر</th><th>الإجمالي</th></tr>"
            f"{rows}</table>"
            f"<h3>الإجمالي: {receipt['total']:.2f}</h3>"
            f"<p>المدفوع: {receipt['paid']:.2f} | الباقي للعميل: {receipt['change']:.2f}</p>"
            "</body></html>"
        )
        from PySide6.QtGui import QTextDocument
        document = QTextDocument()
        document.setHtml(html)
        document.print_(printer)
