"""Arabic RTL product catalog screen with searchable product maintenance."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import SQLAlchemyError

from baynex_stationery.db.session import SessionLocal
from baynex_stationery.services.catalog import (
    create_category,
    create_unit,
    list_categories,
    list_units,
)
from baynex_stationery.services.inventory import (
    create_inventory_count,
    create_inventory_transfer,
    create_warehouse,
    ensure_default_warehouse,
    get_stock_balance,
    issue_stock,
    list_stock_balances,
    list_stock_movements,
    list_warehouses,
    post_inventory_count,
    post_inventory_transfer,
    receive_stock,
    set_inventory_count_line,
    set_warehouse_active,
    update_warehouse,
)
from baynex_stationery.services.products import (
    create_product,
    list_products,
    set_product_active,
    update_product,
)
from baynex_stationery.ui.components import configure_data_table, create_page_heading


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
            "wholesale": QLineEdit(str(product.wholesale_price) if product and product.wholesale_price is not None else ""),
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
        basic_group = QGroupBox("البيانات الأساسية")
        basic_form = QFormLayout(basic_group)
        basic_form.addRow("رمز الصنف *", self.fields["sku"])
        basic_form.addRow("اسم الصنف *", self.fields["name"])
        basic_form.addRow("الباركود", self.fields["barcode"])
        basic_form.addRow("ملاحظات", self.fields["notes"])

        pricing_group = QGroupBox("الأسعار والكميات")
        pricing_form = QFormLayout(pricing_group)
        pricing_form.addRow("سعر التجزئة", self.fields["sale"])
        pricing_form.addRow("سعر الجملة (اختياري)", self.fields["wholesale"])
        pricing_form.addRow("سعر التكلفة", self.fields["cost"])
        if not product:
            pricing_form.addRow("الرصيد الافتتاحي", self.fields["stock"])
        pricing_form.addRow("حد إعادة الطلب", self.fields["minimum"])

        classification_group = QGroupBox("التصنيف ووحدة القياس")
        classification_form = QFormLayout(classification_group)
        classification_form.addRow("التصنيف", self.category)
        classification_form.addRow("وحدة القياس", self.unit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(basic_group)
        layout.addWidget(pricing_group)
        layout.addWidget(classification_group)
        layout.addWidget(buttons)
        self.setMinimumWidth(540)

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
                "wholesale_price": Decimal(self.fields["wholesale"].text().strip()) if self.fields["wholesale"].text().strip() else None,
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


class InventoryCountDialog(QDialog):
    def __init__(self, balances, parent=None):
        super().__init__(parent)
        self.setWindowTitle("جرد المستودع")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(760, 560)
        self.table = QTableWidget(len(balances), 3)
        self.table.setHorizontalHeaderLabels(["اسم الصنف", "الرصيد الدفتري", "الكمية الفعلية"])
        configure_data_table(self.table, stretch_last=True, row_height=40)
        self.table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed)
        for row, (product, balance) in enumerate(balances):
            name = QTableWidgetItem(product.name)
            name.setData(Qt.ItemDataRole.UserRole, product.id)
            name.setFlags(name.flags() & ~Qt.ItemFlag.ItemIsEditable)
            book = QTableWidgetItem(f"{balance:g}")
            book.setFlags(book.flags() & ~Qt.ItemFlag.ItemIsEditable)
            actual = QTableWidgetItem(f"{balance:g}")
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, book)
            self.table.setItem(row, 2, actual)
        self.table.horizontalHeader().setStretchLastSection(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("راجع الرصيد الفعلي لكل صنف، وعدّل الكميات التي تختلف عن الرصيد الدفتري."))
        layout.addWidget(self.table)
        layout.addWidget(buttons)

    def values(self):
        result = []
        for row in range(self.table.rowCount()):
            product_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            try:
                quantity = Decimal(self.table.item(row, 2).text().strip())
            except (InvalidOperation, AttributeError) as exc:
                raise ValueError(f"الكمية الفعلية غير صالحة في السطر {row + 1}") from exc
            if not quantity.is_finite() or quantity < 0:
                raise ValueError(f"الكمية الفعلية يجب ألا تكون سالبة في السطر {row + 1}")
            if quantity != quantity.quantize(Decimal("0.001")):
                raise ValueError(f"الكمية الفعلية تقبل ثلاث خانات عشرية في السطر {row + 1}")
            result.append((product_id, quantity))
        return result


class InventoryMovementsDialog(QDialog):
    """Readable, non-editable movement history for the selected product."""

    MOVEMENT_NAMES: ClassVar[dict[str, str]] = {
        "opening": "رصيد افتتاحي",
        "receipt": "إدخال",
        "issue": "صرف",
        "sale": "بيع",
        "transfer_in": "تحويل وارد",
        "transfer_out": "تحويل صادر",
        "adjustment_in": "تسوية زيادة",
        "adjustment_out": "تسوية نقص",
        "count_in": "زيادة جرد",
        "count_out": "نقص جرد",
    }

    def __init__(self, movements, parent=None):
        super().__init__(parent)
        self.setWindowTitle("سجل حركات المخزون")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(900, 560)

        self.table = QTableWidget(len(movements), 4)
        self.table.setHorizontalHeaderLabels(
            ["التاريخ والوقت", "نوع الحركة", "الكمية", "البيان"]
        )
        configure_data_table(self.table, row_height=40)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setColumnWidth(0, 170)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 110)

        for row, movement in enumerate(movements):
            values = [
                movement.created_at.strftime("%Y-%m-%d %H:%M"),
                self.MOVEMENT_NAMES.get(movement.movement_type, movement.movement_type),
                f"{movement.quantity_delta:+}",
                movement.note or "—",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 2:
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, column, cell)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(
            create_page_heading(
                "سجل حركات المخزون",
                f"عدد الحركات المسجلة لهذا الصنف في المستودع المحدد: {len(movements)}",
                self,
            )
        )
        layout.addWidget(self.table)
        layout.addWidget(buttons)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BAYNEX STATIONERY | نظام القرطاسية")
        self.resize(1280, 800)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QWidget()
        root.setObjectName("applicationRoot")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(7)

        heading = create_page_heading(
            "إدارة الأصناف والمخزون",
            "تعريف الأصناف ومتابعة الأرصدة وحركات المستودعات",
            root,
        )
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(240)
        self.search.setPlaceholderText("بحث سريع: الاسم أو الرمز أو الباركود...")
        self.add_button = QPushButton("جديد")
        self.edit_button = QPushButton("تعديل")
        self.deactivate_button = QPushButton("إيقاف")
        self.category_button = QPushButton("التصنيفات")
        self.unit_button = QPushButton("وحدات القياس")
        self.refresh_button = QPushButton("تحديث")
        self.warehouse = QComboBox()
        self.add_warehouse_button = QPushButton("مستودع جديد")
        self.edit_warehouse_button = QPushButton("تعديل المستودع")
        self.deactivate_warehouse_button = QPushButton("إيقاف المستودع")
        self.receive_button = QPushButton("إدخال")
        self.issue_button = QPushButton("صرف")
        self.transfer_button = QPushButton("تحويل")
        self.count_button = QPushButton("الجرد")
        self.movements_button = QPushButton("الحركات")
        self.sales_button = QPushButton("فاتورة مبيعات")
        self.pos_button = QPushButton("نقطة البيع POS")
        self.purchases_button = QPushButton("المشتريات")

        action_buttons = (
            self.add_button, self.edit_button, self.deactivate_button,
            self.category_button, self.unit_button, self.refresh_button,
            self.pos_button, self.purchases_button, self.add_warehouse_button, self.edit_warehouse_button,
            self.deactivate_warehouse_button, self.receive_button, self.issue_button,
            self.transfer_button, self.count_button, self.movements_button, self.sales_button,
        )
        for button in action_buttons:
            button.setMinimumHeight(29)
            button.setMinimumWidth(68)
        self.add_button.setObjectName("primaryAction")
        self.receive_button.setObjectName("primaryAction")
        self.warehouse.setMinimumWidth(155)
        self.warehouse.setMinimumHeight(29)

        catalog_toolbar = QToolBar("إدارة الأصناف", self)
        catalog_toolbar.setObjectName("catalogToolbar")
        catalog_toolbar.setMovable(False)
        catalog_toolbar.setFloatable(False)
        catalog_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        for button in (
            self.add_button, self.edit_button, self.deactivate_button,
            self.category_button, self.unit_button, self.refresh_button,
        ):
            catalog_toolbar.addWidget(button)
        catalog_toolbar.addWidget(self.sales_button)
        catalog_toolbar.addWidget(self.pos_button)
        catalog_toolbar.addWidget(self.purchases_button)
        catalog_toolbar.addSeparator()
        catalog_toolbar.addWidget(self.search)

        stock_toolbar = QToolBar("عمليات المخزون", self)
        stock_toolbar.setObjectName("stockToolbar")
        stock_toolbar.setMovable(False)
        stock_toolbar.setFloatable(False)
        stock_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        for widget in (
            self.warehouse, self.add_warehouse_button, self.edit_warehouse_button,
            self.deactivate_warehouse_button, self.receive_button, self.issue_button,
            self.transfer_button, self.count_button, self.movements_button,
        ):
            stock_toolbar.addWidget(widget)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, catalog_toolbar)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, stock_toolbar)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["الرمز", "الباركود", "اسم الصنف", "التصنيف", "الوحدة",
             "سعر التكلفة", "سعر التجزئة", "سعر الجملة", "الرصيد"]
        )
        configure_data_table(self.table, row_height=32)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setColumnWidth(0, 105)
        self.table.setColumnWidth(1, 145)
        self.table.setColumnWidth(2, 250)
        self.table.setColumnWidth(3, 150)
        self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 125)
        self.table.setColumnWidth(6, 125)
        self.table.setColumnWidth(7, 125)

        table_frame = QGroupBox("بيانات الأصناف وأرصدة المستودع")
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(6, 10, 6, 6)
        table_layout.addWidget(self.table)

        layout.addWidget(heading)
        layout.addWidget(table_frame, 1)
        self.setCentralWidget(root)

        file_menu = self.menuBar().addMenu("ملف")
        refresh_action = file_menu.addAction("تحديث البيانات")
        refresh_action.triggered.connect(self.refresh_products)
        file_menu.addSeparator()
        exit_action = file_menu.addAction("إغلاق النظام")
        exit_action.triggered.connect(self.close)
        catalog_menu = self.menuBar().addMenu("الأصناف")
        for label, handler in (
            ("إضافة صنف", self.add_product),
            ("تعديل الصنف المحدد", self.edit_product),
            ("إضافة تصنيف", self.add_category),
            ("إضافة وحدة قياس", self.add_unit),
        ):
            action = catalog_menu.addAction(label)
            action.triggered.connect(handler)
        sales_menu = self.menuBar().addMenu("المبيعات")
        sales_action = sales_menu.addAction("فاتورة مبيعات جديدة")
        sales_action.triggered.connect(self.open_sales_invoice)
        pos_action = sales_menu.addAction("نقطة البيع POS")
        pos_action.triggered.connect(self.open_pos)
        purchase_menu = self.menuBar().addMenu("المشتريات")
        purchase_action = purchase_menu.addAction("الموردون وفواتير المشتريات")
        purchase_action.triggered.connect(self.open_purchases)
        accounting_menu = self.menuBar().addMenu("الحسابات")
        accounting_action = accounting_menu.addAction("دليل الحسابات والقيود اليومية")
        accounting_action.triggered.connect(self.open_accounting)
        stock_menu = self.menuBar().addMenu("المخزون")
        for label, handler in (
            ("إدخال مخزون", self.receive_selected),
            ("صرف مخزون", self.issue_selected),
            ("تحويل مخزون", self.transfer_selected),
            ("جرد المستودع", self.count_selected),
            ("سجل الحركات", self.show_movements),
        ):
            action = stock_menu.addAction(label)
            action.triggered.connect(handler)
        help_menu = self.menuBar().addMenu("مساعدة")
        about_action = help_menu.addAction("حول BAYNEX")
        about_action.triggered.connect(
            lambda: QMessageBox.information(
                self, "حول BAYNEX", "BAYNEX STATIONERY\\nنظام إدارة القرطاسية والمخزون"
            )
        )

        self.add_button.clicked.connect(self.add_product)
        self.edit_button.clicked.connect(self.edit_product)
        self.deactivate_button.clicked.connect(self.deactivate_product)
        self.category_button.clicked.connect(self.add_category)
        self.unit_button.clicked.connect(self.add_unit)
        self.refresh_button.clicked.connect(self.refresh_products)
        self.add_warehouse_button.clicked.connect(self.add_warehouse)
        self.edit_warehouse_button.clicked.connect(self.edit_warehouse)
        self.deactivate_warehouse_button.clicked.connect(self.deactivate_warehouse)
        self.receive_button.clicked.connect(self.receive_selected)
        self.issue_button.clicked.connect(self.issue_selected)
        self.transfer_button.clicked.connect(self.transfer_selected)
        self.count_button.clicked.connect(self.count_selected)
        self.movements_button.clicked.connect(self.show_movements)
        self.sales_button.clicked.connect(self.open_sales_invoice)
        self.pos_button.clicked.connect(self.open_pos)
        self.purchases_button.clicked.connect(self.open_purchases)
        self.search.textChanged.connect(self.refresh_products)
        self.warehouse.currentIndexChanged.connect(self.refresh_products)
        self._refresh_warehouses()
        self.table.doubleClicked.connect(self.edit_product)
        self.refresh_products()


    def open_sales_invoice(self):
        from baynex_stationery.ui.sales_dialog import SalesInvoiceDialog

        dialog = SalesInvoiceDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_products()

    def open_accounting(self):
        from baynex_stationery.ui.accounting_dialog import AccountingDialog

        dialog = AccountingDialog(self)
        dialog.exec()

    def open_purchases(self):
        from baynex_stationery.ui.purchases_dialog import PurchasesDialog

        dialog = PurchasesDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_products()

    def open_pos(self):
        from baynex_stationery.ui.pos_dialog import POSDialog

        dialog = POSDialog(self)
        dialog.exec()
        self.refresh_products()

    def _refresh_warehouses(self):
        with SessionLocal.begin() as session:
            default = ensure_default_warehouse(session)
            warehouses = list_warehouses(session, include_inactive=True)
        selected = self.warehouse.currentData()
        self.warehouse.clear()
        for item in warehouses:
            label = item.name if item.is_active else f"{item.name} (متوقف)"
            self.warehouse.addItem(label, item.id)
            self.warehouse.setItemData(
                self.warehouse.count() - 1, item.is_active, Qt.ItemDataRole.UserRole + 1
            )
        index = self.warehouse.findData(selected if selected is not None else default.id)
        if index >= 0:
            self.warehouse.setCurrentIndex(index)

    def _inventory_product_id(self):
        product_id = self._selected_product_id()
        if product_id is None:
            QMessageBox.information(self, "المخزون", "حدد صنفاً من الجدول أولاً")
            return None
        if self.warehouse.currentData() is None:
            QMessageBox.warning(self, "المخزون", "لا يوجد مستودع محدد")
            return None
        if not self.warehouse.currentData(Qt.ItemDataRole.UserRole + 1):
            QMessageBox.warning(self, "المخزون", "المستودع المحدد متوقف؛ فعّله أولاً")
            return None
        return product_id

    def add_warehouse(self):
        code, accepted = QInputDialog.getText(self, "إضافة مستودع", "رمز المستودع:")
        if not accepted:
            return
        name, accepted = QInputDialog.getText(self, "إضافة مستودع", "اسم المستودع:")
        if not accepted:
            return
        try:
            with SessionLocal.begin() as session:
                create_warehouse(session, code=code, name=name)
            self._refresh_warehouses()
            QMessageBox.information(self, "المستودعات", "تم إنشاء المستودع")
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر إنشاء المستودع", str(exc))

    def edit_warehouse(self):
        warehouse_id = self.warehouse.currentData()
        if warehouse_id is None:
            return
        with SessionLocal() as session:
            from baynex_stationery.db.models import Warehouse
            warehouse = session.get(Warehouse, warehouse_id)
            if warehouse is None:
                return
            old_code, old_name = warehouse.code, warehouse.name
        code, accepted = QInputDialog.getText(
            self, "تعديل المستودع", "رمز المستودع:", text=old_code
        )
        if not accepted:
            return
        name, accepted = QInputDialog.getText(
            self, "تعديل المستودع", "اسم المستودع:", text=old_name
        )
        if not accepted:
            return
        try:
            with SessionLocal.begin() as session:
                update_warehouse(session, warehouse_id, code=code, name=name)
            self._refresh_warehouses()
            QMessageBox.information(self, "المستودعات", "تم تحديث بيانات المستودع")
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر تعديل المستودع", str(exc))

    def deactivate_warehouse(self):
        warehouse_id = self.warehouse.currentData()
        if warehouse_id is None:
            return
        active = bool(self.warehouse.currentData(Qt.ItemDataRole.UserRole + 1))
        action = "إيقاف" if active else "تفعيل"
        answer = QMessageBox.question(
            self, f"{action} المستودع",
            f"هل تريد {action} المستودع المحدد؟ لا يمكن إيقاف المستودع الافتراضي أو مستودع لديه رصيد.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            with SessionLocal.begin() as session:
                set_warehouse_active(session, warehouse_id, not active)
            self._refresh_warehouses()
            self.refresh_products()
            QMessageBox.information(self, "المستودعات", f"تم {action} المستودع")
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر إيقاف المستودع", str(exc))

    def _manual_quantity(self, title):
        value, accepted = QInputDialog.getText(self, title, "أدخل الكمية (حتى 3 خانات عشرية):")
        if not accepted:
            return None
        try:
            amount = Decimal(value.strip())
            if not amount.is_finite() or amount < 0:
                raise ValueError
            return amount
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, title, "أدخل كمية رقمية صحيحة غير سالبة")
            return None

    def receive_selected(self):
        product_id = self._inventory_product_id()
        if product_id is None:
            return
        quantity = self._manual_quantity("إدخال مخزون")
        if quantity is None or quantity == 0:
            return
        try:
            with SessionLocal.begin() as session:
                receive_stock(
                    session, product_id=product_id, warehouse_id=self.warehouse.currentData(),
                    quantity=quantity, note="إدخال يدوي من شاشة المخزون",
                )
            self.refresh_products()
            QMessageBox.information(self, "المخزون", "تم تسجيل إدخال المخزون")
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر إدخال المخزون", str(exc))

    def issue_selected(self):
        product_id = self._inventory_product_id()
        if product_id is None:
            return
        quantity = self._manual_quantity("صرف مخزون")
        if quantity is None or quantity == 0:
            return
        try:
            with SessionLocal.begin() as session:
                issue_stock(
                    session, product_id=product_id, warehouse_id=self.warehouse.currentData(),
                    quantity=quantity, note="صرف يدوي من شاشة المخزون",
                )
            self.refresh_products()
            QMessageBox.information(self, "المخزون", "تم تسجيل صرف المخزون")
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر صرف المخزون", str(exc))

    def transfer_selected(self):
        product_id = self._inventory_product_id()
        if product_id is None:
            return
        with SessionLocal() as session:
            destinations = [
                item for item in list_warehouses(session)
                if item.id != self.warehouse.currentData()
            ]
        if not destinations:
            QMessageBox.information(self, "تحويل المخزون", "أنشئ مستودعاً آخر أولاً")
            return
        names = [item.name for item in destinations]
        name, accepted = QInputDialog.getItem(
            self, "تحويل المخزون", "المستودع الوجهة:", names, 0, False
        )
        if not accepted:
            return
        destination = next(item for item in destinations if item.name == name)
        quantity = self._manual_quantity("تحويل المخزون")
        if quantity is None or quantity == 0:
            return
        try:
            with SessionLocal.begin() as session:
                transfer = create_inventory_transfer(
                    session,
                    number=f"TR-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                    source_warehouse_id=self.warehouse.currentData(),
                    destination_warehouse_id=destination.id,
                    lines=[{"product_id": product_id, "quantity": quantity}],
                    note="تحويل من شاشة المخزون",
                )
                post_inventory_transfer(session, transfer_id=transfer.id)
            self.refresh_products()
            QMessageBox.information(self, "تحويل المخزون", "تم ترحيل التحويل بنجاح")
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر التحويل", str(exc))

    def count_selected(self):
        warehouse_id = self.warehouse.currentData()
        if warehouse_id is None or not self.warehouse.currentData(Qt.ItemDataRole.UserRole + 1):
            QMessageBox.warning(self, "الجرد", "اختر مستودعاً نشطاً أولاً")
            return
        with SessionLocal() as session:
            balances = list_stock_balances(session, warehouse_id=warehouse_id)
        if not balances:
            QMessageBox.information(self, "الجرد", "لا توجد أصناف نشطة لجردها")
            return
        dialog = InventoryCountDialog(balances, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            counted_values = dialog.values()
        except ValueError as exc:
            QMessageBox.warning(self, "بيانات الجرد غير صحيحة", str(exc))
            return
        difference_total = sum(
            (counted - balance for (_product, balance), (_product_id, counted)
             in zip(balances, counted_values, strict=True)),
            Decimal(0),
        )
        answer = QMessageBox.question(
            self, "تأكيد ترحيل الجرد",
            f"عدد الأصناف: {len(counted_values)}\nصافي فرق الكميات: {difference_total:+g}\n"
            "سيتم إنشاء حركات تسوية لكل فرق. هل تريد الترحيل؟",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            with SessionLocal.begin() as session:
                count = create_inventory_count(
                    session,
                    number=f"CO-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                    warehouse_id=warehouse_id,
                    note="جرد شامل من شاشة المخزون",
                    snapshot=[(product.id, balance) for product, balance in balances],
                )
                for product_id, counted in counted_values:
                    set_inventory_count_line(
                        session, count_id=count.id, product_id=product_id,
                        counted_quantity=counted,
                    )
                post_inventory_count(session, count_id=count.id)
            self.refresh_products()
            QMessageBox.information(self, "الجرد", "تم ترحيل الجرد وتسجيل فروق المخزون")
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر ترحيل الجرد", str(exc))

    def show_movements(self):
        product_id = self._inventory_product_id()
        if product_id is None:
            return
        with SessionLocal() as session:
            movements = list_stock_movements(
                session, product_id=product_id, warehouse_id=self.warehouse.currentData()
            )
        if not movements:
            QMessageBox.information(
                self,
                "سجل حركات المخزون",
                "لا توجد حركات مسجلة لهذا الصنف في المستودع المحدد.",
            )
            return
        InventoryMovementsDialog(movements, self).exec()

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
                    f"{product.wholesale_price:.2f}" if product.wholesale_price is not None else "—",
                    f"{get_stock_balance(session, product.id, self.warehouse.currentData()):g}",
                ]
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(str(value))
                    if column == 0:
                        cell.setData(Qt.ItemDataRole.UserRole, product.id)
                    if column in (5, 6, 7, 8):
                        cell.setTextAlignment(
                            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                        )
                    self.table.setItem(row, column, cell)
        self.statusBar().showMessage(f"عدد الأصناف المعروضة: {len(products)}")

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
            values = dialog.values()
            values["opening_warehouse_id"] = self.warehouse.currentData()
            with SessionLocal.begin() as session:
                create_product(session, **values)
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
