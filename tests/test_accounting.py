from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from baynex_stationery.db.base import Base
from baynex_stationery.services.accounting import (
    account_ledger,
    create_account,
    create_journal_entry,
    list_journal_entries,
    post_journal_entry,
    trial_balance,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def make_accounts(session):
    cash = create_account(session, code="1000", name="الصندوق", account_type="asset")
    capital = create_account(session, code="3000", name="رأس المال", account_type="equity")
    return cash, capital


def test_post_balanced_journal_and_trial_balance(session):
    cash, capital = make_accounts(session)
    entry = create_journal_entry(
        session, number="JE-001", description="إثبات رأس المال",
        lines=[
            {"account_id": cash.id, "debit": "1000.00"},
            {"account_id": capital.id, "credit": "1000.00"},
        ],
    )
    assert entry.status == "draft"
    post_journal_entry(session, entry_id=entry.id)
    balances = {row["code"]: row for row in trial_balance(session)}
    assert balances["1000"]["debit"] == Decimal("1000.00")
    assert balances["1000"]["balance"] == Decimal("1000.00")
    assert balances["3000"]["credit"] == Decimal("1000.00")
    assert balances["3000"]["balance"] == Decimal("1000.00")
    assert len(list_journal_entries(session, status="posted")) == 1


def test_unbalanced_journal_cannot_be_posted(session):
    cash, capital = make_accounts(session)
    entry = create_journal_entry(
        session, number="JE-002", description="قيد غير متوازن",
        lines=[
            {"account_id": cash.id, "debit": "100.00"},
            {"account_id": capital.id, "credit": "90.00"},
        ],
    )
    with pytest.raises(ValueError, match="غير متوازن"):
        post_journal_entry(session, entry_id=entry.id)
    assert entry.status == "draft"


def test_journal_rejects_double_sided_or_duplicate_lines(session):
    cash, capital = make_accounts(session)
    with pytest.raises(ValueError, match="مديناً أو دائناً فقط"):
        create_journal_entry(
            session, number="JE-003", description="سطر مزدوج",
            lines=[
                {"account_id": cash.id, "debit": "10.00", "credit": "10.00"},
                {"account_id": capital.id, "credit": "10.00"},
            ],
        )
    with pytest.raises(ValueError, match="لا تكرر الحساب"):
        create_journal_entry(
            session, number="JE-004", description="حساب مكرر",
            lines=[
                {"account_id": cash.id, "debit": "10.00"},
                {"account_id": cash.id, "credit": "10.00"},
            ],
        )


def test_draft_journals_do_not_appear_in_ledger_or_trial_balance(session):
    cash, capital = make_accounts(session)
    create_journal_entry(
        session, number="JE-005", description="مسودة",
        lines=[
            {"account_id": cash.id, "debit": "50.00"},
            {"account_id": capital.id, "credit": "50.00"},
        ],
    )
    balances = {row["code"]: row for row in trial_balance(session)}
    assert balances["1000"]["debit"] == Decimal("0.00")
    assert account_ledger(session, account_id=cash.id) == []
