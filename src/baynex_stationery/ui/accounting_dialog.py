"""Arabic chart-of-accounts, journal-entry, and trial-balance screen."""
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
from baynex_stationery.services.accounting import (
    account_ledger,
    create_account,
    create_journal_entry,
    list_accounts,
    post_journal_entry,
    trial_balance,
)
from baynex_stationery.ui.components import configure_data_table, create_page_heading


class AccountingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("الحسابات والقيود اليومية | BAYNEX")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(1120, 720)

        root = QVBoxLayout(self)
        root.addWidget(create_page_heading(
            "الحسابات والقيود اليومية",
            "دليل الحسابات، قيود اليومية المزدوجة، وميزان المراجعة للأرصدة المرحلة",
            self,
        ))
        actions = QHBoxLayout()
        self.add_account_button = QPushButton("حساب جديد")
        self.add_journal_button = QPushButton("قيد يومية جديد")
        self.refresh_button = QPushButton("تحديث")
        self.add_journal_button.setObjectName("primaryAction")
        actions.addWidget(self.add_account_button)
        actions.addWidget(self.add_journal_button)
        actions.addStretch(1)
        actions.addWidget(self.refresh_button)
        root.addLayout(actions)

        accounts_box = QGroupBox("دليل الحسابات")
        accounts_layout = QVBoxLayout(accounts_box)
        self.accounts_table = QTableWidget(0, 4)
        self.accounts_table.setHorizontalHeaderLabels(["رمز الحساب", "اسم الحساب", "نوع الحساب", "الحالة"])
        configure_data_table(self.accounts_table, row_height=32)
        self.accounts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        accounts_layout.addWidget(self.accounts_table)
        root.addWidget(accounts_box, 1)

        balance_box = QGroupBox("ميزان المراجعة — القيود المرحلة فقط")
        balance_layout = QVBoxLayout(balance_box)
        self.balance_table = QTableWidget(0, 6)
        self.balance_table.setHorizontalHeaderLabels(
            ["رمز الحساب", "اسم الحساب", "النوع", "إجمالي المدين", "إجمالي الدائن", "الرصيد الطبيعي"]
        )
        configure_data_table(self.balance_table, row_height=32)
        self.balance_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        balance_layout.addWidget(self.balance_table)
        root.addWidget(balance_box, 2)

        self.add_account_button.clicked.connect(self.add_account)
        self.add_journal_button.clicked.connect(self.add_journal)
        self.refresh_button.clicked.connect(self.refresh_data)
        self.refresh_data()

    def refresh_data(self):
        with SessionLocal() as session:
            accounts = list_accounts(session, include_inactive=True)
            balances = trial_balance(session)
        account_types = {
            "asset": "أصول", "liability": "التزامات", "equity": "حقوق ملكية",
            "revenue": "إيرادات", "expense": "مصروفات",
        }
        self.accounts_table.setRowCount(len(accounts))
        for row, account in enumerate(accounts):
            values = [
                account.code, account.name, account_types.get(account.account_type, account.account_type),
                "نشط" if account.is_active else "متوقف",
            ]
            for column, value in enumerate(values):
                self.accounts_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.balance_table.setRowCount(len(balances))
        for row, item in enumerate(balances):
            values = [
                item["code"], item["name"], account_types.get(item["account_type"], item["account_type"]),
                f'{item["debit"]:.2f}', f'{item["credit"]:.2f}', f'{item["balance"]:.2f}',
            ]
            for column, value in enumerate(values):
                self.balance_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.accounts_table.resizeColumnsToContents()
        self.balance_table.resizeColumnsToContents()

    def add_account(self):
        code, ok = QInputDialog.getText(self, "حساب جديد", "رمز الحساب:")
        if not ok:
            return
        name, ok = QInputDialog.getText(self, "حساب جديد", "اسم الحساب:")
        if not ok:
            return
        kind = QComboBox(self)
        for label, value in (
            ("أصول", "asset"), ("التزامات", "liability"), ("حقوق ملكية", "equity"),
            ("إيرادات", "revenue"), ("مصروفات", "expense"),
        ):
            kind.addItem(label, value)
        from PySide6.QtWidgets import QDialog as QtDialog, QDialogButtonBox

        chooser = QtDialog(self)
        chooser.setWindowTitle("نوع الحساب")
        layout = QVBoxLayout(chooser)
        layout.addWidget(kind)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(chooser.accept)
        buttons.rejected.connect(chooser.reject)
        layout.addWidget(buttons)
        if chooser.exec() != QtDialog.DialogCode.Accepted:
            return
        try:
            with SessionLocal.begin() as session:
                create_account(session, code=code, name=name, account_type=kind.currentData())
            self.refresh_data()
        except (ValueError, SQLAlchemyError) as exc:
            QMessageBox.warning(self, "تعذر إنشاء الحساب", str(exc))

    def add_journal(self):
        with SessionLocal() as session:
            accounts = list_accounts(session)
        if len(accounts) < 2:
            QMessageBox.information(self, "قيد يومية", "أنشئ حسابين على الأقل قبل إدخال القيد")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("قيد يومية جديد")
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dialog.resize(540, 420)
        form = QFormLayout(dialog)
        number = QLineEdit(f"JE-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        description = QLineEdit()
        debit_account = QComboBox()
        credit_account = QComboBox()
        for account in accounts:
            label = f"{account.code} | {account.name}"
            debit_account.addItem(label, account.id)
            credit_account.addItem(label, account.id)
        amount = QLineEdit("0.00")
        form.addRow("رقم القيد", number)
        form.addRow("البيان", description)
        form.addRow("الحساب المدين", debit_account)
        form.addRow("الحساب الدائن", credit_account)
        form.addRow("المبلغ", amount)
        buttons = QHBoxLayout()
        save = QPushButton("حفظ وترحيل القيد")
        save.setObjectName("primaryAction")
        cancel = QPushButton("إلغاء")
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        form.addRow(buttons)
        cancel.clicked.connect(dialog.reject)

        def save_entry():
            try:
                value = Decimal(amount.text().strip())
                if not value.is_finite() or value <= 0 or value != value.quantize(Decimal("0.01")):
                    raise ValueError("المبلغ يجب أن يكون موجباً وبخانتين عشريتين")
                if debit_account.currentData() == credit_account.currentData():
                    raise ValueError("اختر حسابين مختلفين")
                with SessionLocal.begin() as session:
                    entry = create_journal_entry(
                        session, number=number.text(), description=description.text(),
                        lines=[
                            {"account_id": debit_account.currentData(), "debit": value},
                            {"account_id": credit_account.currentData(), "credit": value},
                        ],
                    )
                    post_journal_entry(session, entry_id=entry.id)
                dialog.accept()
            except (ValueError, InvalidOperation, SQLAlchemyError) as exc:
                QMessageBox.warning(dialog, "تعذر ترحيل القيد", str(exc))

        save.clicked.connect(save_entry)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_data()
