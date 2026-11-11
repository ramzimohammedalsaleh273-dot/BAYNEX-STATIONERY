"""ERP-style Arabic point-of-sale screen for BAYNEX STATIONERY."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import SQLAlchemyError

from baynex_stationery.db.session import SessionLocal
from baynex_stationery.services.inventory import ensure_default_warehouse, list_warehouses
from baynex_stationery.services.pos import calculate_line, calculate_totals, decimal_input
from baynex_stationery.services.products import list_products
from baynex_stationery.services.sales import create_sale, post_sale
from baynex_stationery.ui.components import configure_data_table


class POSPaymentDialog(QDialog):
    """Confirm tender and calculate cash change before posting."""

    def __init__(self, total: Decimal, parent=None):
        super().__init__(parent)
        self.setWindowTitle("الدفع وإنهاء البيع")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(430)
        self.total = total
        self.method = QComboBox()
        for label, value in (("نقدي", "cash"), ("شبكة / بطاقة", "card"),
                             ("تحويل", "transfer"), ("آجل", "credit")):
            self.method.addItem(label, value)
        self.received = QLineEdit(f"{total:.2f}")
        self.due = QLabel(f"{total:,.2f}")
        self.change = QLabel("0.00")
        self.due.setObjectName("posGrandTotal")
        self.change.setObjectName("posChange")
        form = QFormLayout()
        form.addRow("المبلغ المستحق:", self.due)
        form.addRow("طريقة الدفع:", self.method)
        form.addRow("المبلغ المستلم:", self.received)
        form.addRow("الباقي للعميل:", self.change)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("تأكيد الدفع والترحيل")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("إلغاء")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("مراجعة بيانات التحصيل"))
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
            self.change.setText(f"{max(Decimal(0), amount - self.total):,.2f}")
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
    """A single-document, full-width ERP cashier layout with transactional posting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BAYNEX STATIONERY | فاتورة مبيعات - نقطة البيع")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(1360, 820)
        self.setMinimumSize(1000, 650)
        self.cart: dict[int, dict] = {}
        self.held_tickets: list[dict] = []
        with SessionLocal.begin() as session:
            ensure_default_warehouse(session)
            self.products = list_products(session)
            self.warehouses = list_warehouses(session)
        self.product_by_id = {p.id: p for p in self.products}
        self.product_by_code = {
            code: p for p in self.products for code in (p.sku, p.barcode) if code
        }

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(5)

        # Compact ERP document toolbar.
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        self.new_button = QPushButton("جديد")
        self.hold_button = QPushButton("تعليق")
        self.restore_button = QPushButton("استرجاع")
        self.print_button = QPushButton("طباعة")
        self.refresh_button = QPushButton("تحديث الأصناف")
        for button in (self.new_button, self.hold_button, self.restore_button,
                       self.print_button, self.refresh_button):
            button.setMinimumHeight(30)
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        toolbar.addWidget(QLabel("BAYNEX  |  إدارة المبيعات"))
        root.addLayout(toolbar)

        self.tabs = QTabWidget()
        main_tab = QWidget()
        main_grid = QGridLayout(main_tab)
        main_grid.setContentsMargins(8, 8, 8, 8)
        main_grid.setHorizontalSpacing(12)
        main_grid.setVerticalSpacing(7)

        self.invoice_no = QLineEdit(f"POS-{datetime.now():%Y%m%d-%H%M%S}")
        self.invoice_date = QLineEdit(datetime.now().strftime("%d/%m/%Y %H:%M"))
        self.invoice_date.setReadOnly(True)
        self.warehouse = QComboBox()
        for warehouse in self.warehouses:
            self.warehouse.addItem(warehouse.name, warehouse.id)
        self.payment_method = QComboBox()
        for label, value in (("نقدي", "cash"), ("شبكة / بطاقة", "card"),
                             ("تحويل", "transfer"), ("آجل", "credit")):
            self.payment_method.addItem(label, value)
        self.customer = QLineEdit("عميل نقدي")
        self.customer_phone = QLineEdit()
        self.customer.setMinimumWidth(190)

        fields = [
            ("رقم الفاتورة", self.invoice_no), ("التاريخ", self.invoice_date),
            ("المستودع", self.warehouse), ("طريقة الدفع", self.payment_method),
            ("اسم العميل", self.customer), ("رقم الهاتف", self.customer_phone),
        ]
        for index, (caption, widget) in enumerate(fields):
            row, col = divmod(index, 3)
            label = QLabel(caption)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            main_grid.addWidget(label, row * 2, col * 2 + 1)
            main_grid.addWidget(widget, row * 2, col * 2)
        for col in range(6):
            main_grid.setColumnStretch(col, 1 if col % 2 == 0 else 0)
        self.tabs.addTab(main_tab, "البيانات الرئيسية")

        extra_tab = QWidget()
        extra_grid = QGridLayout(extra_tab)
        self.invoice_note = QLineEdit()
        self.invoice_note.setPlaceholderText("ملاحظات الفاتورة...")
        extra_grid.addWidget(QLabel("البيان / ملاحظات الفاتورة"), 0, 1)
        extra_grid.addWidget(self.invoice_note, 0, 0)
        self.tabs.addTab(extra_tab, "بيانات إضافية")
        root.addWidget(self.tabs)

        # Item entry row, followed by the full-width invoice grid.
        entry = QHBoxLayout()
        self.barcode = QLineEdit()
        self.barcode.setObjectName("posBarcode")
        self.barcode.setPlaceholderText("امسح الباركود أو أدخل رمز الصنف ثم اضغط Enter")
        self.barcode.setMinimumHeight(36)
        self.product_picker = QComboBox()
        self.product_picker.setEditable(True)
        self.product_picker.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.product_picker.setMinimumWidth(360)
        self.product_picker.setPlaceholderText("ابحث عن الصنف بالاسم أو الرمز...")
        self._fill_product_picker()
        self.add_button = QPushButton("إضافة الصنف")
        self.add_button.setMinimumHeight(36)
        entry.addWidget(QLabel("الباركود:"))
        entry.addWidget(self.barcode, 2)
        entry.addWidget(QLabel("اختيار الصنف:"))
        entry.addWidget(self.product_picker, 3)
        entry.addWidget(self.add_button)
        root.addLayout(entry)

        root.addWidget(QLabel("تفاصيل الأصناف — اكتب رمز الصنف أو الباركود في أول صف فارغ، ثم اضغط Enter أو انتقل للخلية التالية"))
        self.cart_table = QTableWidget(12, 9)
        self.cart_table.setObjectName("posInvoiceGrid")
        self.cart_table.setHorizontalHeaderLabels(
            ["م", "رمز الصنف", "الباركود", "اسم الصنف", "الوحدة", "الكمية", "السعر", "الخصم", "الإجمالي"]
        )
        configure_data_table(self.cart_table, row_height=36)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.cart_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.cart_table.setColumnWidth(0, 42)
        self.cart_table.setColumnWidth(1, 112)
        self.cart_table.setColumnWidth(2, 132)
        self.cart_table.setColumnWidth(3, 300)
        self.cart_table.setColumnWidth(4, 82)
        self.cart_table.setColumnWidth(5, 90)
        self.cart_table.setColumnWidth(6, 105)
        self.cart_table.setColumnWidth(7, 92)
        self.cart_table.setColumnWidth(8, 125)
        self.cart_table.setStyleSheet(
            "QTableWidget#posInvoiceGrid { background:#FFFFFF; gridline-color:#B8C5CF; }"
            "QTableWidget#posInvoiceGrid QHeaderView::section {"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #F7FAFC,stop:1 #D5E0E8);"
            "color:#183F5A; border:1px solid #AAB9C5; padding:7px; font-weight:700; }"
            "QTableWidget#posInvoiceGrid::item { padding:5px; border-bottom:1px solid #E0E7EC; }"
            "QTableWidget#posInvoiceGrid::item:selected { background:#C5E2F4; color:#153D58; }"
        )
        self.cart_table.itemChanged.connect(self._cart_edited)
        root.addWidget(self.cart_table, 1)

        # Lower document area mirrors the reference: totals at left, customer
        # and document information at right.
        lower = QHBoxLayout()
        lower.setSpacing(8)
        totals_box = QGroupBox("ملخص الفاتورة")
        totals_grid = QGridLayout(totals_box)
        self.subtotal_label = QLabel("0.00")
        self.discount_label = QLabel("0.00")
        self.tax_label = QLabel("0.00")
        self.total_label = QLabel("0.00")
        self.total_label.setObjectName("posGrandTotal")
        self.paid_preview = QLabel("0.00")
        self.change_preview = QLabel("0.00")
        for row, (caption, widget) in enumerate((
            ("القيمة قبل الخصم", self.subtotal_label),
            ("إجمالي الخصم", self.discount_label),
            ("الضريبة", self.tax_label),
            ("الصافي المستحق", self.total_label),
            ("المبلغ المدفوع", self.paid_preview),
            ("الباقي", self.change_preview),
        )):
            totals_grid.addWidget(QLabel(caption), row, 1)
            totals_grid.addWidget(widget, row, 0)
            widget.setMinimumWidth(130)
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lower.addWidget(totals_box, 2)

        customer_box = QGroupBox("بيانات العميل والعملية")
        customer_grid = QGridLayout(customer_box)
        self.customer_summary = QLabel("عميل نقدي")
        self.item_count = QLabel("0")
        self.quantity_total = QLabel("0.000")
        self.status_label = QLabel("فاتورة جديدة")
        for row, (caption, widget) in enumerate((
            ("العميل", self.customer_summary), ("عدد الأصناف", self.item_count),
            ("إجمالي الكمية", self.quantity_total), ("حالة العملية", self.status_label),
        )):
            customer_grid.addWidget(QLabel(caption), row, 1)
            customer_grid.addWidget(widget, row, 0)
        lower.addWidget(customer_box, 3)
        root.addLayout(lower)

        actions = QHBoxLayout()
        self.remove_button = QPushButton("حذف السطر")
        self.qty_button = QPushButton("تعديل الكمية")
        self.clear_button = QPushButton("تفريغ الفاتورة")
        self.pay_button = QPushButton("حفظ وترحيل البيع  F8")
        self.pay_button.setObjectName("primaryAction")
        self.pay_button.setMinimumHeight(38)
        for button in (self.remove_button, self.qty_button, self.clear_button,
                       self.hold_button, self.restore_button, self.print_button):
            actions.addWidget(button)
        actions.addStretch(1)
        actions.addWidget(self.pay_button)
        root.addLayout(actions)

        self.new_button.clicked.connect(self.new_ticket)
        self.hold_button.clicked.connect(self.hold_ticket)
        self.restore_button.clicked.connect(self.restore_ticket)
        self.print_button.clicked.connect(self.print_receipt)
        self.refresh_button.clicked.connect(self.reload_products)
        self.add_button.clicked.connect(self.add_selected_product)
        self.barcode.returnPressed.connect(self.scan_barcode)
        self.product_picker.lineEdit().returnPressed.connect(self.add_selected_product)
        self.remove_button.clicked.connect(self.remove_selected)
        self.qty_button.clicked.connect(self.edit_quantity)
        self.clear_button.clicked.connect(self.new_ticket)
        self.pay_button.clicked.connect(self.checkout)
        self.customer.textChanged.connect(self.customer_summary.setText)
        self.render_cart()

        for sequence, callback in (
            ("F2", lambda: self.barcode.setFocus()),
            ("F4", self.hold_ticket),
            ("F6", self.restore_ticket),
            ("F8", self.checkout),
            ("F9", self.print_receipt),
            ("Delete", self.remove_selected),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
        self.barcode.setFocus()

    def _fill_product_picker(self):
        self.product_picker.clear()
        for product in self.products:
            self.product_picker.addItem(f"{product.sku} - {product.name}", product.id)
        completer = self.product_picker.completer()
        if completer:
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)

    def reload_products(self):
        with SessionLocal() as session:
            self.products = list_products(session)
        self.product_by_id = {p.id: p for p in self.products}
        self.product_by_code = {
            code: p for p in self.products for code in (p.sku, p.barcode) if code
        }
        self._fill_product_picker()
        self.status_label.setText("تم تحديث قائمة الأصناف")

    def scan_barcode(self):
        code = self.barcode.text().strip()
        if not code:
            return
        product = self.product_by_code.get(code)
        if product is None:
            QMessageBox.information(self, "الصنف غير موجود", f"لم يتم العثور على صنف بالرمز: {code}")
            self.barcode.selectAll()
            return
        self.add_product(product.id)
        self.barcode.clear()
        self.barcode.setFocus()

    def add_selected_product(self):
        text = self.product_picker.currentText().strip()
        current_index = self.product_picker.currentIndex()
        selected_text = (
            self.product_picker.itemText(current_index) if current_index >= 0 else ""
        )
        product_id = (
            self.product_picker.itemData(current_index)
            if text == selected_text and current_index >= 0 else None
        )
        if product_id is None:
            product = self.product_by_code.get(text)
            if product is None:
                product = next(
                    (p for p in self.products if f"{p.sku} - {p.name}" == text or p.name == text),
                    None,
                )
            product_id = product.id if product else None
        if product_id is None:
            QMessageBox.information(self, "اختيار الصنف", "اختر صنفاً صحيحاً من قائمة الأصناف.")
            return
        self.add_product(int(product_id))
        self.barcode.setFocus()

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
        """Render committed invoice lines plus ready-to-type blank rows."""
        self.cart_table.blockSignals(True)
        visible_rows = max(12, len(self.cart) + 5)
        self.cart_table.setRowCount(visible_rows)
        for row in range(visible_rows):
            for column in range(9):
                cell = QTableWidgetItem("")
                cell.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                )
                if column not in (1, 2):
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.cart_table.setItem(row, column, cell)

        for row, (product_id, line) in enumerate(self.cart.items()):
            product = line["product"]
            unit = product.unit_record.symbol if product.unit_record else product.unit
            calc = calculate_line(line["quantity"], line["unit_price"], line["discount"])
            values = [
                str(row + 1), product.sku, product.barcode or "", product.name, unit,
                f'{line["quantity"]:.3f}', f'{line["unit_price"]:.2f}',
                f'{line["discount"]:.2f}', f'{calc["total"]:.2f}',
            ]
            for column, value in enumerate(values):
                cell = self.cart_table.item(row, column)
                cell.setText(value)
                if column == 1:
                    cell.setData(Qt.ItemDataRole.UserRole, product_id)
                if column in (5, 6, 7):
                    cell.setFlags(cell.flags() | Qt.ItemFlag.ItemIsEditable)
                if column not in (1, 2, 5, 6, 7):
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)

        self.cart_table.blockSignals(False)
        self.recalculate()

    def _cart_edited(self, item):
        """Resolve SKU/barcode directly in the grid or validate editable line values."""
        if item.row() < 0:
            return
        if item.column() in (1, 2):
            code = item.text().strip()
            if not code:
                return
            product = self.product_by_code.get(code)
            if product is None:
                self.status_label.setText(f"لم يتم العثور على الصنف ذي الرمز: {code}")
                item.setToolTip("أدخل رمز صنف أو باركود مسجلاً في دليل الأصناف")
                return
            self.add_product(product.id)
            next_row = len(self.cart)
            self.cart_table.setCurrentCell(next_row, 1)
            self.cart_table.setFocus()
            self.status_label.setText(f"تمت إضافة: {product.name} — أدخل الصنف التالي")
            return

        if item.column() not in (5, 6, 7):
            return
        key_item = self.cart_table.item(item.row(), 1)
        product_id = key_item.data(Qt.ItemDataRole.UserRole) if key_item else None
        if product_id not in self.cart:
            return
        try:
            calc = calculate_line(
                self.cart_table.item(item.row(), 5).text(),
                self.cart_table.item(item.row(), 6).text(),
                self.cart_table.item(item.row(), 7).text(),
            )
            self.cart[product_id].update(
                {key: calc[key] for key in ("quantity", "unit_price", "discount")}
            )
            self.render_cart()
            self.cart_table.setCurrentCell(item.row(), item.column())
        except (ValueError, AttributeError):
            QMessageBox.warning(
                self, "تفاصيل الصنف",
                "تحقق من الكمية والسعر والخصم ثم أعد الإدخال."
            )
            self.render_cart()

    def recalculate(self):
        lines = [
            calculate_line(line["quantity"], line["unit_price"], line["discount"])
            for line in self.cart.values()
        ]
        totals = calculate_totals(lines)
        self.subtotal_label.setText(f'{totals["subtotal"]:,.2f}')
        self.discount_label.setText(f'{totals["discount"]:,.2f}')
        self.tax_label.setText("0.00")
        self.total_label.setText(f'{totals["total"]:,.2f}')
        self.paid_preview.setText(f'{totals["total"]:,.2f}')
        self.change_preview.setText("0.00")
        self.item_count.setText(str(len(self.cart)))
        self.quantity_total.setText(f'{sum((x["quantity"] for x in self.cart.values()), Decimal(0)):.3f}')

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
        if row >= 0:
            self.cart_table.editItem(self.cart_table.item(row, 5))

    def new_ticket(self):
        if self.cart and QMessageBox.question(
            self, "فاتورة جديدة", "هل تريد تفريغ الفاتورة الحالية؟"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.cart.clear()
        self.customer.setText("عميل نقدي")
        self.customer_phone.clear()
        self.invoice_note.clear()
        self.invoice_no.setText(f"POS-{datetime.now():%Y%m%d-%H%M%S}")
        self.invoice_date.setText(datetime.now().strftime("%d/%m/%Y %H:%M"))
        self.status_label.setText("فاتورة جديدة")
        self.render_cart()
        self.barcode.setFocus()

    def hold_ticket(self):
        if not self.cart:
            QMessageBox.information(self, "تعليق الفاتورة", "لا توجد أصناف لتعليقها.")
            return
        self.held_tickets.append({
            "cart": {key: dict(value) for key, value in self.cart.items()},
            "customer": self.customer.text(),
            "phone": self.customer_phone.text(),
            "warehouse_id": self.warehouse.currentData(),
            "number": self.invoice_no.text(),
            "note": self.invoice_note.text(),
        })
        self.cart.clear()
        self.new_ticket_after_hold()
        self.render_cart()
        QMessageBox.information(
            self, "تعليق الفاتورة",
            f"تم تعليق الفاتورة. عدد الفواتير المعلقة: {len(self.held_tickets)}",
        )

    def new_ticket_after_hold(self):
        self.customer.setText("عميل نقدي")
        self.customer_phone.clear()
        self.invoice_note.clear()
        self.invoice_no.setText(f"POS-{datetime.now():%Y%m%d-%H%M%S}")
        self.invoice_date.setText(datetime.now().strftime("%d/%m/%Y %H:%M"))

    def restore_ticket(self):
        if not self.held_tickets:
            QMessageBox.information(self, "استرجاع الفاتورة", "لا توجد فواتير معلقة في جلسة الكاشير الحالية.")
            return
        if self.cart and QMessageBox.question(
            self, "استرجاع", "سيتم تعليق السلة الحالية تلقائياً. متابعة؟"
        ) != QMessageBox.StandardButton.Yes:
            return
        if self.cart:
            self.held_tickets.append({
                "cart": self.cart, "customer": self.customer.text(),
                "phone": self.customer_phone.text(),
                "warehouse_id": self.warehouse.currentData(), "number": self.invoice_no.text(),
                "note": self.invoice_note.text(),
            })
        ticket = self.held_tickets.pop()
        self.cart = ticket["cart"]
        self.customer.setText(ticket["customer"])
        self.customer_phone.setText(ticket["phone"])
        self.invoice_note.setText(ticket["note"])
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
            calculate_line(line["quantity"], line["unit_price"], line["discount"])
            for line in self.cart.values()
        ])
        payment = POSPaymentDialog(totals["total"], self)
        payment.method.setCurrentIndex(max(0, payment.method.findData(self.payment_method.currentData())))
        if payment.exec() != QDialog.DialogCode.Accepted:
            return
        lines = [{
            "product_id": product_id, "quantity": line["quantity"],
            "unit_price": line["unit_price"], "discount": line["discount"],
        } for product_id, line in self.cart.items()]
        try:
            with SessionLocal.begin() as session:
                sale = create_sale(
                    session,
                    number=self.invoice_no.text(),
                    warehouse_id=self.warehouse.currentData(),
                    lines=lines,
                    customer_name=self.customer.text().strip() or "عميل نقدي",
                    customer_phone=self.customer_phone.text().strip() or None,
                    payment_method=payment.payment_method,
                    paid_amount=payment.paid_amount,
                    notes=self.invoice_note.text().strip() or None,
                )
                post_sale(session, sale_id=sale.id)
                self.last_receipt = {
                    "number": sale.number, "customer": sale.customer_name,
                    "date": sale.invoice_date.strftime("%Y-%m-%d %H:%M"),
                    "lines": [
                        (item.product_name, item.quantity, item.unit_price, item.line_total)
                        for item in sale.items
                    ],
                    "total": sale.total, "paid": sale.paid_amount,
                    "change": payment.change_amount,
                }
            self.payment_method.setCurrentIndex(
                max(0, self.payment_method.findData(payment.payment_method))
            )
            QMessageBox.information(
                self, "تم البيع بنجاح",
                f"الفاتورة: {self.last_receipt['number']}\n"
                f"الإجمالي: {totals['total']:,.2f}\n"
                f"الباقي للعميل: {payment.change_amount:,.2f}\n"
                "تم تسجيل البيع وخصم المخزون وتسجيل التحصيل ضمن معاملة واحدة.",
            )
            self.cart.clear()
            self.new_ticket_after_hold()
            self.status_label.setText("تم ترحيل الفاتورة بنجاح")
            self.render_cart()
            self.barcode.setFocus()
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر إتمام البيع", str(exc))

    def print_receipt(self):
        receipt = getattr(self, "last_receipt", None)
        if not receipt:
            QMessageBox.information(
                self, "طباعة الإيصال", "لا توجد فاتورة مكتملة للطباعة في هذه الجلسة."
            )
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("طباعة إيصال البيع")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        rows = "".join(
            f"<tr><td>{escape(str(name))}</td><td>{qty}</td>"
            f"<td>{price:.2f}</td><td>{total:.2f}</td></tr>"
            for name, qty, price, total in receipt["lines"]
        )
        document = (
            "<html><meta charset='utf-8'><body dir='rtl'>"
            "<h2>BAYNEX STATIONERY</h2><h3>إيصال بيع</h3>"
            f"<p>رقم الفاتورة: {escape(receipt['number'])}</p>"
            f"<p>العميل: {escape(receipt['customer'])}</p>"
            f"<p>التاريخ: {escape(receipt['date'])}</p>"
            "<table border='1' cellspacing='0' cellpadding='5'>"
            "<tr><th>الصنف</th><th>الكمية</th><th>السعر</th><th>الإجمالي</th></tr>"
            f"{rows}</table><h3>الإجمالي: {receipt['total']:.2f}</h3>"
            f"<p>المدفوع: {receipt['paid']:.2f} | الباقي: {receipt['change']:.2f}</p>"
            "</body></html>"
        )
        from PySide6.QtGui import QTextDocument

        doc = QTextDocument()
        doc.setHtml(document)
        doc.print_(printer)
