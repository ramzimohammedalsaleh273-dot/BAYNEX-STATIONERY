"""Arabic cashbox, bank, receipt, payment, and transfer workspace."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
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
from baynex_stationery.services.accounting import list_accounts
from baynex_stationery.services.treasury import (
    create_treasury_account,
    create_treasury_voucher,
    list_treasury_accounts,
    list_treasury_vouchers,
    treasury_balance,
    treasury_summary,
)
from baynex_stationery.ui.components import configure_data_table, create_page_heading


class TreasuryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("الصناديق والبنوك والسندات | BAYNEX")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(1180, 760)
        root = QVBoxLayout(self)
        root.addWidget(create_page_heading(
            "إدارة الصناديق والبنوك",
            "سندات قبض وصرف وتحويل داخلي مرتبطة بقيود اليومية والأرصدة الفعلية",
            self,
        ))

        actions = QHBoxLayout()
        self.add_account_button = QPushButton("صندوق / بنك جديد")
        self.refresh_button = QPushButton("تحديث الأرصدة والسندات")
        self.add_account_button.setObjectName("primaryAction")
        actions.addWidget(self.add_account_button)
        actions.addStretch(1)
        actions.addWidget(self.refresh_button)
        root.addLayout(actions)

        summary_box = QGroupBox("ملخص الأرصدة")
        summary_layout = QHBoxLayout(summary_box)
        self.cash_total = QLabel("0.00")
        self.bank_total = QLabel("0.00")
        self.grand_total = QLabel("0.00")
        for label, value in (
            ("إجمالي الصناديق:", self.cash_total),
            ("إجمالي البنوك:", self.bank_total),
            ("إجمالي النقدية والبنوك:", self.grand_total),
        ):
            summary_layout.addWidget(QLabel(label))
            value.setMinimumWidth(120)
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            summary_layout.addWidget(value)
        root.addWidget(summary_box)

        accounts_box = QGroupBox("حسابات الصناديق والبنوك")
        accounts_layout = QVBoxLayout(accounts_box)
        self.accounts_table = QTableWidget(0, 5)
        self.accounts_table.setHorizontalHeaderLabels(
            ["الرمز", "اسم الحساب", "النوع", "حساب الأستاذ", "الرصيد الحالي"]
        )
        configure_data_table(self.accounts_table, row_height=34)
        self.accounts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        accounts_layout.addWidget(self.accounts_table)
        root.addWidget(accounts_box, 1)

        voucher_box = QGroupBox("إدخال سند جديد")
        form = QFormLayout(voucher_box)
        self.voucher_number = QLineEdit(f"TV-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        self.voucher_type = QComboBox()
        for label, value in (("سند قبض", "receipt"), ("سند صرف", "payment"), ("تحويل داخلي", "transfer")):
            self.voucher_type.addItem(label, value)
        self.source_account = QComboBox()
        self.destination_account = QComboBox()
        self.counter_account = QComboBox()
        self.amount = QLineEdit("0.00")
        self.description = QLineEdit()
        form.addRow("رقم السند *", self.voucher_number)
        form.addRow("نوع السند *", self.voucher_type)
        form.addRow("الصندوق / البنك *", self.source_account)
        form.addRow("الوجهة (للتحويل)", self.destination_account)
        form.addRow("الحساب المقابل (للقبض/الصرف)", self.counter_account)
        form.addRow("المبلغ *", self.amount)
        form.addRow("البيان *", self.description)
        root.addWidget(voucher_box)

        footer = QHBoxLayout()
        self.post_button = QPushButton("حفظ وترحيل السند")
        self.post_button.setObjectName("primaryAction")
        close_button = QPushButton("إغلاق")
        footer.addStretch(1)
        footer.addWidget(self.post_button)
        footer.addWidget(close_button)
        root.addLayout(footer)

        history_box = QGroupBox("سجل السندات المرحلة")
        history_layout = QVBoxLayout(history_box)
        self.history_table = QTableWidget(0, 7)
        self.history_table.setHorizontalHeaderLabels(
            ["التاريخ", "رقم السند", "النوع", "من حساب", "إلى / مقابل", "المبلغ", "البيان"]
        )
        configure_data_table(self.history_table, row_height=32)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        history_layout.addWidget(self.history_table)
        root.addWidget(history_box, 2)

        self.voucher_type.currentIndexChanged.connect(self.update_voucher_fields)
        self.add_account_button.clicked.connect(self.add_account)
        self.refresh_button.clicked.connect(self.refresh_data)
        self.post_button.clicked.connect(self.post_voucher)
        close_button.clicked.connect(self.reject)
        self.refresh_data()

    def update_voucher_fields(self):
        transfer = self.voucher_type.currentData() == "transfer"
        self.destination_account.setEnabled(transfer)
        self.counter_account.setEnabled(not transfer)

    def refresh_data(self):
        with SessionLocal() as session:
            accounts = list_treasury_accounts(session, include_inactive=True)
            ledger_accounts = list_accounts(session)
            vouchers = list_treasury_vouchers(session, limit=500)
            summary = treasury_summary(session)
            balances = {
                item.id: treasury_balance(session, treasury_account_id=item.id)
                for item in accounts if item.is_active
            }
        self.accounts_table.setRowCount(len(accounts))
        for row, item in enumerate(accounts):
            kind = "صندوق" if item.account_kind == "cash" else "بنك"
            values = [
                item.code, item.name, kind,
                f"{item.ledger_account.code} | {item.ledger_account.name}",
                f"{balances.get(item.id, Decimal('0.00')):.2f}",
            ]
            for column, value in enumerate(values):
                self.accounts_table.setItem(row, column, QTableWidgetItem(str(value)))

        self.source_account.clear()
        self.destination_account.clear()
        for item in accounts:
            if item.is_active:
                label = f"{item.code} | {item.name}"
                self.source_account.addItem(label, item.id)
                self.destination_account.addItem(label, item.id)
        self.counter_account.clear()
        for item in ledger_accounts:
            self.counter_account.addItem(f"{item.code} | {item.name}", item.id)

        self.cash_total.setText(f"{summary['cash_total']:.2f}")
        self.bank_total.setText(f"{summary['bank_total']:.2f}")
        self.grand_total.setText(f"{summary['grand_total']:.2f}")
        type_names = {"receipt": "قبض", "payment": "صرف", "transfer": "تحويل"}
        self.history_table.setRowCount(len(vouchers))
        for row, item in enumerate(vouchers):
            if item.voucher_type == "transfer":
                counterpart = item.destination_account.name if item.destination_account else "—"
            else:
                counterpart = item.counter_account.name if item.counter_account else "—"
            values = [
                item.voucher_date.strftime("%Y-%m-%d"),
                item.number,
                type_names.get(item.voucher_type, item.voucher_type),
                item.treasury_account.name if item.treasury_account else "—",
                counterpart, f"{item.amount:.2f}", item.description,
            ]
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.accounts_table.resizeColumnsToContents()
        self.history_table.resizeColumnsToContents()
        self.update_voucher_fields()

    def add_account(self):
        code, ok = QInputDialog.getText(self, "حساب صندوق / بنك جديد", "رمز الحساب:")
        if not ok:
            return
        name, ok = QInputDialog.getText(self, "حساب صندوق / بنك جديد", "اسم الحساب:")
        if not ok:
            return
        kind = QComboBox(self)
        kind.addItem("صندوق نقدي", "cash")
        kind.addItem("حساب بنكي", "bank")
        chooser = QDialog(self)
        chooser.setWindowTitle("نوع الحساب")
        chooser.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(chooser)
        layout.addWidget(kind)
        from PySide6.QtWidgets import QDialogButtonBox
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(chooser.accept)
        buttons.rejected.connect(chooser.reject)
        layout.addWidget(buttons)
        if chooser.exec() != QDialog.DialogCode.Accepted:
            return
        ledger_code, ok = QInputDialog.getText(self, "حساب الأستاذ", "رمز حساب الأستاذ (مثال 1010):")
        if not ok:
            return
        opening, ok = QInputDialog.getText(self, "الرصيد الافتتاحي", "الرصيد الافتتاحي:", text="0.00")
        if not ok:
            return
        try:
            with SessionLocal.begin() as session:
                create_treasury_account(
                    session, code=code, name=name, account_kind=kind.currentData(),
                    ledger_code=ledger_code, opening_balance=opening,
                )
            self.refresh_data()
        except (ValueError, InvalidOperation, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر إنشاء الحساب", str(exc))

    def post_voucher(self):
        try:
            value = Decimal(self.amount.text().strip())
            if not value.is_finite() or value <= 0 or value != value.quantize(Decimal("0.01")):
                raise ValueError("المبلغ يجب أن يكون موجباً وبخانتين عشريتين")
            kind = self.voucher_type.currentData()
            with SessionLocal.begin() as session:
                voucher = create_treasury_voucher(
                    session, number=self.voucher_number.text(), voucher_type=kind,
                    treasury_account_id=self.source_account.currentData(),
                    destination_account_id=self.destination_account.currentData() if kind == "transfer" else None,
                    counter_account_id=self.counter_account.currentData() if kind != "transfer" else None,
                    amount=value, description=self.description.text(),
                )
                number, journal_number = voucher.number, voucher.journal_entry.number
            QMessageBox.information(
                self, "تم ترحيل السند",
                f"رقم السند: {number}\nالقيد المحاسبي: {journal_number}\n"
                "تم تحديث رصيد الصندوق أو البنك في دفتر الأستاذ.",
            )
            self.voucher_number.setText(f"TV-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
            self.amount.setText("0.00")
            self.description.clear()
            self.refresh_data()
        except (ValueError, InvalidOperation, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر ترحيل السند", str(exc))
