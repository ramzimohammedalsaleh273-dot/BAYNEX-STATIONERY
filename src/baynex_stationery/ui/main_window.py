"""Arabic RTL product catalog screen with searchable product maintenance."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
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
        self.warehouse = QComboBox()
        self.add_warehouse_button = QPushButton("إضافة مستودع")
        self.edit_warehouse_button = QPushButton("تعديل المستودع")
        self.deactivate_warehouse_button = QPushButton("إيقاف المستودع")
        self.receive_button = QPushButton("إدخال مخزون")
        self.issue_button = QPushButton("صرف مخزون")
        self.transfer_button = QPushButton("تحويل")
        self.count_button = QPushButton("جرد الصنف")
        self.movements_button = QPushButton("سجل الحركات")
        for widget in (
            self.add_button, self.edit_button, self.deactivate_button,
            self.category_button, self.unit_button, self.refresh_button,
        ):
            toolbar.addWidget(widget)
        toolbar.addWidget(self.search, 1)

        inventory_toolbar = QHBoxLayout()
        for widget in (
            self.warehouse, self.add_warehouse_button, self.edit_warehouse_button,
            self.deactivate_warehouse_button,
            self.receive_button, self.issue_button, self.transfer_button,
            self.count_button, self.movements_button,
        ):
            inventory_toolbar.addWidget(widget)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["الرمز", "الباركود", "اسم الصنف", "التصنيف", "الوحدة", "سعر التكلفة", "سعر البيع", "رصيد المستودع"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(header)
        layout.addWidget(subtitle)
        layout.addLayout(toolbar)
        layout.addLayout(inventory_toolbar)
        layout.addWidget(self.table)
        self.setCentralWidget(root)

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
        self.search.textChanged.connect(self.refresh_products)
        self.warehouse.currentIndexChanged.connect(self.refresh_products)
        self._refresh_warehouses()
        self.table.doubleClicked.connect(self.edit_product)
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
        product_id = self._inventory_product_id()
        if product_id is None:
            return
        quantity = self._manual_quantity("جرد الصنف")
        if quantity is None:
            return
        with SessionLocal() as session:
            book_quantity = get_stock_balance(session, product_id, self.warehouse.currentData())
        difference = quantity - book_quantity
        answer = QMessageBox.question(
            self, "تأكيد الجرد",
            f"الرصيد الدفتري: {book_quantity:g}\\nالكمية الفعلية: {quantity:g}\\nالفرق: {difference:+g}\\nهل تريد اعتماد التسوية؟",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            with SessionLocal.begin() as session:
                count = create_inventory_count(
                    session,
                    number=f"CO-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                    warehouse_id=self.warehouse.currentData(),
                    note="جرد من شاشة المخزون",
                )
                set_inventory_count_line(
                    session, count_id=count.id, product_id=product_id,
                    counted_quantity=quantity,
                )
                post_inventory_count(session, count_id=count.id)
            self.refresh_products()
            QMessageBox.information(self, "الجرد", "تم اعتماد فرق الجرد وتسجيل حركة التسوية")
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
            message = "لا توجد حركات مسجلة لهذا الصنف في المستودع المحدد."
        else:
            message = "\n".join(
                f"{item.created_at:%Y-%m-%d %H:%M} | {item.movement_type} | "
                f"{item.quantity_delta:+} | {item.note or ''}"
                for item in movements
            )
        QMessageBox.information(self, "سجل حركات المخزون", message)

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
                    f"{get_stock_balance(session, product.id, self.warehouse.currentData()):g}",
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
