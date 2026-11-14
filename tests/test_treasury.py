from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from baynex_stationery.db.base import Base
from baynex_stationery.services.accounting import create_account
from baynex_stationery.services.treasury import (
    create_treasury_account, create_treasury_voucher, list_treasury_vouchers,
    treasury_balance, treasury_summary,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def setup_cash(session):
    cash = create_treasury_account(
        session, code="CASH1", name="الصندوق الرئيسي", account_kind="cash",
        ledger_code="1010", opening_balance="1000.00",
    )
    expense = create_account(
        session, code="5100", name="مصروفات تشغيلية", account_type="expense",
    )
    revenue = create_account(
        session, code="4100", name="إيرادات أخرى", account_type="revenue",
    )
    return cash, expense, revenue


def test_opening_balance_and_receipt_are_reflected_in_ledger(session):
    cash, expense, revenue = setup_cash(session)
    assert treasury_balance(session, treasury_account_id=cash.id) == Decimal("1000.00")
    receipt = create_treasury_voucher(
        session, number="RC-001", voucher_type="receipt",
        treasury_account_id=cash.id, counter_account_id=revenue.id,
        amount="250.00", description="تحصيل إيراد",
    )
    assert receipt.status == "posted"
    assert treasury_balance(session, treasury_account_id=cash.id) == Decimal("1250.00")
    assert len(list_treasury_vouchers(session)) == 1


def test_payment_cannot_overdraw_cash_and_valid_payment_posts_journal(session):
    cash, expense, _ = setup_cash(session)
    with pytest.raises(ValueError, match="غير كافٍ"):
        create_treasury_voucher(
            session, number="PV-001", voucher_type="payment",
            treasury_account_id=cash.id, counter_account_id=expense.id,
            amount="1001.00", description="مصروف زائد",
        )
    voucher = create_treasury_voucher(
        session, number="PV-002", voucher_type="payment",
        treasury_account_id=cash.id, counter_account_id=expense.id,
        amount="200.00", description="مصروف تشغيل",
    )
    assert voucher.journal_entry.status == "posted"
    assert treasury_balance(session, treasury_account_id=cash.id) == Decimal("800.00")


def test_internal_transfer_moves_balance_between_cash_and_bank(session):
    cash, _, _ = setup_cash(session)
    bank = create_treasury_account(
        session, code="BANK1", name="البنك التجاري", account_kind="bank",
        ledger_code="1020",
    )
    transfer = create_treasury_voucher(
        session, number="TR-001", voucher_type="transfer",
        treasury_account_id=cash.id, destination_account_id=bank.id,
        amount="350.00", description="إيداع في البنك",
    )
    assert transfer.status == "posted"
    assert treasury_balance(session, treasury_account_id=cash.id) == Decimal("650.00")
    assert treasury_balance(session, treasury_account_id=bank.id) == Decimal("350.00")
    summary = treasury_summary(session)
    assert summary["cash_total"] == Decimal("650.00")
    assert summary["bank_total"] == Decimal("350.00")
    assert summary["grand_total"] == Decimal("1000.00")


def test_transfer_requires_distinct_accounts_and_cannot_overdraw(session):
    cash, _, _ = setup_cash(session)
    bank = create_treasury_account(
        session, code="BANK2", name="بنك آخر", account_kind="bank", ledger_code="1021",
    )
    with pytest.raises(ValueError, match="الحساب نفسه"):
        create_treasury_voucher(
            session, number="TR-002", voucher_type="transfer",
            treasury_account_id=cash.id, destination_account_id=cash.id,
            amount="1.00", description="تحويل ذاتي",
        )
    with pytest.raises(ValueError, match="غير كافٍ"):
        create_treasury_voucher(
            session, number="TR-003", voucher_type="transfer",
            treasury_account_id=bank.id, destination_account_id=cash.id,
            amount="1.00", description="رصيد غير كاف",
        )
