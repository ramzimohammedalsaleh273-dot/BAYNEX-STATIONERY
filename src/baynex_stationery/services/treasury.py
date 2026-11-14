"""Cashbox and bank voucher services backed by balanced posted journal entries."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from baynex_stationery.db.models import (
    Account,
    JournalEntry,
    JournalLine,
    TreasuryAccount,
    TreasuryVoucher,
)
from baynex_stationery.services.accounting import (
    create_account,
    create_journal_entry,
    post_journal_entry,
)

CENT = Decimal("0.01")
TREASURY_KINDS = {"cash", "bank"}
VOUCHER_TYPES = {"receipt", "payment", "transfer"}


def _amount(value) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("المبلغ غير صالح") from exc
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(CENT):
        raise ValueError("المبلغ يجب أن يكون موجباً وبخانتين عشريتين")
    return amount


def create_treasury_account(
    session: Session, *, code: str, name: str, account_kind: str,
    ledger_code: str, opening_balance: Decimal | str | int = Decimal(0),
) -> TreasuryAccount:
    clean_code, clean_name = code.strip().upper(), name.strip()
    if not clean_code or len(clean_code) > 32:
        raise ValueError("رمز الصندوق أو البنك مطلوب ولا يتجاوز 32 حرفاً")
    if not clean_name or len(clean_name) > 160:
        raise ValueError("اسم الصندوق أو البنك مطلوب ولا يتجاوز 160 حرفاً")
    if account_kind not in TREASURY_KINDS:
        raise ValueError("نوع الحساب يجب أن يكون صندوقاً أو بنكاً")
    opening = Decimal(str(opening_balance))
    if not opening.is_finite() or opening < 0 or opening != opening.quantize(CENT):
        raise ValueError("الرصيد الافتتاحي يجب أن يكون غير سالب وبخانتين عشريتين")
    ledger = create_account(
        session, code=ledger_code, name=clean_name,
        account_type="asset",
    )
    treasury = TreasuryAccount(
        code=clean_code, name=clean_name, account_kind=account_kind,
        ledger_account_id=ledger.id,
    )
    session.add(treasury)
    session.flush()
    if opening:
        equity = session.scalar(select(Account).where(Account.code == "3000"))
        if equity is None:
            equity = create_account(
                session, code="3000", name="رأس المال الافتتاحي", account_type="equity",
            )
        entry = create_journal_entry(
            session, number=f"OPEN-{clean_code}", description=f"رصيد افتتاحي: {clean_name}",
            lines=[
                {"account_id": ledger.id, "debit": opening},
                {"account_id": equity.id, "credit": opening},
            ],
            source_type="treasury_opening", source_id=treasury.id,
        )
        post_journal_entry(session, entry_id=entry.id)
    return treasury


def list_treasury_accounts(session: Session, *, include_inactive: bool = False) -> list[TreasuryAccount]:
    statement = select(TreasuryAccount).options(
        joinedload(TreasuryAccount.ledger_account)
    ).order_by(TreasuryAccount.account_kind, TreasuryAccount.code)
    if not include_inactive:
        statement = statement.where(TreasuryAccount.is_active.is_(True))
    return list(session.scalars(statement).unique())


def treasury_balance(session: Session, *, treasury_account_id: int) -> Decimal:
    treasury = session.get(TreasuryAccount, treasury_account_id)
    if treasury is None:
        raise ValueError("الصندوق أو البنك غير موجود")
    debit, credit = session.execute(
        select(
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(
            JournalLine.account_id == treasury.ledger_account_id,
            JournalEntry.status == "posted",
        )
    ).one()
    return (Decimal(debit) - Decimal(credit)).quantize(CENT)


def create_treasury_voucher(
    session: Session, *, number: str, voucher_type: str, treasury_account_id: int,
    amount: Decimal | str | int, description: str, counter_account_id: int | None = None,
    destination_account_id: int | None = None, voucher_date: datetime | None = None,
) -> TreasuryVoucher:
    clean_number, clean_description = number.strip(), description.strip()
    if not clean_number or len(clean_number) > 40:
        raise ValueError("رقم السند مطلوب ولا يتجاوز 40 حرفاً")
    if not clean_description or len(clean_description) > 240:
        raise ValueError("بيان السند مطلوب ولا يتجاوز 240 حرفاً")
    if voucher_type not in VOUCHER_TYPES:
        raise ValueError("نوع السند غير معروف")
    value = _amount(amount)
    source = session.get(TreasuryAccount, treasury_account_id)
    if source is None or not source.is_active:
        raise ValueError("الصندوق أو البنك المصدر غير موجود أو متوقف")
    if voucher_type == "transfer":
        destination = session.get(TreasuryAccount, destination_account_id)
        if destination is None or not destination.is_active:
            raise ValueError("حساب الوجهة غير موجود أو متوقف")
        if destination.id == source.id:
            raise ValueError("لا يمكن التحويل إلى الحساب نفسه")
        if counter_account_id is not None:
            raise ValueError("التحويل الداخلي لا يقبل حساباً مقابلاً")
        if treasury_balance(session, treasury_account_id=source.id) < value:
            raise ValueError("الرصيد غير كافٍ لإتمام التحويل")
        debit_id, credit_id = destination.ledger_account_id, source.ledger_account_id
    else:
        if destination_account_id is not None or counter_account_id is None:
            raise ValueError("اختر حساباً مقابلاً واحداً للسند")
        counter = session.get(Account, counter_account_id)
        if counter is None or not counter.is_active:
            raise ValueError("الحساب المقابل غير موجود أو متوقف")
        if counter.id == source.ledger_account_id:
            raise ValueError("الحساب المقابل يجب أن يختلف عن حساب الصندوق أو البنك")
        if voucher_type == "receipt":
            debit_id, credit_id = source.ledger_account_id, counter.id
        else:
            if treasury_balance(session, treasury_account_id=source.id) < value:
                raise ValueError("الرصيد غير كافٍ لصرف هذا المبلغ")
            debit_id, credit_id = counter.id, source.ledger_account_id
        destination = None
    entry = create_journal_entry(
        session, number=f"TV-{clean_number}", description=clean_description,
        lines=[
            {"account_id": debit_id, "debit": value},
            {"account_id": credit_id, "credit": value},
        ],
        entry_date=voucher_date or datetime.now(UTC),
        source_type="treasury_voucher", source_id=None,
    )
    post_journal_entry(session, entry_id=entry.id)
    voucher = TreasuryVoucher(
        number=clean_number, voucher_type=voucher_type, treasury_account_id=source.id,
        destination_account_id=destination.id if destination else None,
        counter_account_id=counter_account_id, amount=value,
        voucher_date=voucher_date or datetime.now(UTC), description=clean_description,
        status="posted", journal_entry_id=entry.id,
    )
    session.add(voucher)
    session.flush()
    entry.source_id = voucher.id
    session.flush()
    return voucher


def list_treasury_vouchers(
    session: Session, *, treasury_account_id: int | None = None, limit: int = 500,
) -> list[TreasuryVoucher]:
    statement = select(TreasuryVoucher).options(
        joinedload(TreasuryVoucher.treasury_account),
        joinedload(TreasuryVoucher.destination_account),
        joinedload(TreasuryVoucher.counter_account),
    ).order_by(TreasuryVoucher.voucher_date.desc(), TreasuryVoucher.id.desc()).limit(
        max(1, min(int(limit), 5000))
    )
    if treasury_account_id is not None:
        statement = statement.where(
            (TreasuryVoucher.treasury_account_id == treasury_account_id)
            | (TreasuryVoucher.destination_account_id == treasury_account_id)
        )
    return list(session.scalars(statement).unique())


def treasury_summary(session: Session) -> dict:
    accounts = list_treasury_accounts(session)
    balances = [
        {"id": item.id, "code": item.code, "name": item.name,
         "kind": item.account_kind, "balance": treasury_balance(session, treasury_account_id=item.id)}
        for item in accounts
    ]
    return {
        "accounts": balances,
        "cash_total": sum((row["balance"] for row in balances if row["kind"] == "cash"), Decimal("0.00")),
        "bank_total": sum((row["balance"] for row in balances if row["kind"] == "bank"), Decimal("0.00")),
        "grand_total": sum((row["balance"] for row in balances), Decimal("0.00")),
    }
