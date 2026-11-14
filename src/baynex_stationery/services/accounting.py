"""Double-entry accounting services with immutable posted journals."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from baynex_stationery.db.models import Account, JournalEntry, JournalLine
from baynex_stationery.domain.pricing import money

ACCOUNT_TYPES = {"asset", "liability", "equity", "revenue", "expense"}
CENT = Decimal("0.01")


def _money(value, label: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} غير صالح") from exc
    if not amount.is_finite() or amount < 0 or amount != amount.quantize(CENT):
        raise ValueError(f"{label} يجب أن يكون غير سالب وبخانتين عشريتين")
    return amount


def create_account(
    session: Session, *, code: str, name: str, account_type: str,
    parent_id: int | None = None,
) -> Account:
    clean_code, clean_name = code.strip(), name.strip()
    if not clean_code or len(clean_code) > 32:
        raise ValueError("رمز الحساب مطلوب ولا يتجاوز 32 حرفاً")
    if not clean_name or len(clean_name) > 160:
        raise ValueError("اسم الحساب مطلوب ولا يتجاوز 160 حرفاً")
    if account_type not in ACCOUNT_TYPES:
        raise ValueError("نوع الحساب غير معروف")
    if parent_id is not None:
        parent = session.get(Account, parent_id)
        if parent is None or not parent.is_active:
            raise ValueError("الحساب الأب غير موجود أو غير نشط")
    account = Account(
        code=clean_code, name=clean_name, account_type=account_type, parent_id=parent_id,
    )
    session.add(account)
    session.flush()
    return account


def list_accounts(
    session: Session, *, account_type: str | None = None, include_inactive: bool = False,
) -> list[Account]:
    statement = select(Account).order_by(Account.code.asc())
    if not include_inactive:
        statement = statement.where(Account.is_active.is_(True))
    if account_type:
        statement = statement.where(Account.account_type == account_type)
    return list(session.scalars(statement))


def set_account_active(session: Session, *, account_id: int, active: bool) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise ValueError("الحساب غير موجود")
    if not active:
        has_posted_lines = session.scalar(
            select(JournalLine.id).join(JournalEntry)
            .where(JournalLine.account_id == account_id, JournalEntry.status == "posted")
            .limit(1)
        )
        if has_posted_lines is not None:
            raise ValueError("لا يمكن إيقاف حساب له قيود مرحلة؛ استخدم حساباً بديلاً")
    account.is_active = bool(active)
    session.flush()
    return account


def create_journal_entry(
    session: Session, *, number: str, description: str, lines: list[dict],
    entry_date: datetime | None = None, source_type: str | None = None,
    source_id: int | None = None,
) -> JournalEntry:
    clean_number, clean_description = number.strip(), description.strip()
    if not clean_number or len(clean_number) > 40:
        raise ValueError("رقم القيد مطلوب ولا يتجاوز 40 حرفاً")
    if not clean_description or len(clean_description) > 240:
        raise ValueError("بيان القيد مطلوب ولا يتجاوز 240 حرفاً")
    if len(lines) < 2:
        raise ValueError("القيد المحاسبي يحتاج إلى سطرين على الأقل")
    entry = JournalEntry(
        number=clean_number, description=clean_description,
        entry_date=entry_date or datetime.now(UTC),
        source_type=source_type, source_id=source_id,
    )
    seen: set[int] = set()
    for index, row in enumerate(lines, 1):
        account_id = int(row["account_id"])
        if account_id in seen:
            raise ValueError("لا تكرر الحساب نفسه في القيد؛ اجمع المبلغ في سطر واحد")
        seen.add(account_id)
        account = session.get(Account, account_id)
        if account is None or not account.is_active:
            raise ValueError(f"الحساب في السطر {index} غير موجود أو غير نشط")
        debit = _money(row.get("debit", 0), f"مدين السطر {index}")
        credit = _money(row.get("credit", 0), f"دائن السطر {index}")
        if (debit > 0) == (credit > 0):
            raise ValueError(f"السطر {index} يجب أن يحتوي مديناً أو دائناً فقط")
        entry.lines.append(JournalLine(
            account_id=account_id, description=(row.get("description") or "").strip() or None,
            debit=debit, credit=credit,
        ))
    session.add(entry)
    session.flush()
    return entry


def post_journal_entry(session: Session, *, entry_id: int) -> JournalEntry:
    entry = session.scalar(
        select(JournalEntry).options(joinedload(JournalEntry.lines))
        .where(JournalEntry.id == entry_id).with_for_update()
    )
    if entry is None or entry.status != "draft":
        raise ValueError("القيد غير موجود أو سبق ترحيله")
    if len(entry.lines) < 2:
        raise ValueError("القيد يحتاج إلى سطرين على الأقل")
    debit_total = money(sum((line.debit for line in entry.lines), Decimal("0.00")))
    credit_total = money(sum((line.credit for line in entry.lines), Decimal("0.00")))
    if debit_total <= 0 or debit_total != credit_total:
        raise ValueError("القيد غير متوازن؛ يجب أن يتساوى إجمالي المدين والدائن")
    entry.status = "posted"
    entry.posted_at = datetime.now(UTC)
    session.flush()
    return entry


def list_journal_entries(
    session: Session, *, status: str | None = None, limit: int = 500,
) -> list[JournalEntry]:
    statement = select(JournalEntry).options(joinedload(JournalEntry.lines)).order_by(
        JournalEntry.entry_date.desc(), JournalEntry.id.desc()
    ).limit(max(1, min(int(limit), 5000)))
    if status:
        statement = statement.where(JournalEntry.status == status)
    return list(session.scalars(statement).unique())


def trial_balance(session: Session) -> list[dict]:
    """Return posted debit/credit totals and net balance per account."""
    rows = session.execute(
        select(
            Account.id, Account.code, Account.name, Account.account_type,
            func.coalesce(func.sum(JournalLine.debit), 0).label("debit"),
            func.coalesce(func.sum(JournalLine.credit), 0).label("credit"),
        )
        .outerjoin(JournalLine, JournalLine.account_id == Account.id)
        .outerjoin(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(Account.is_active.is_(True))
        .where((JournalEntry.id.is_(None)) | (JournalEntry.status == "posted"))
        .group_by(Account.id, Account.code, Account.name, Account.account_type)
        .order_by(Account.code.asc())
    ).all()
    return [
        {
            "account_id": row.id, "code": row.code, "name": row.name,
            "account_type": row.account_type,
            "debit": money(row.debit), "credit": money(row.credit),
            "balance": money(Decimal(str(row.debit)) - Decimal(str(row.credit))),
        }
        for row in rows
    ]


def account_ledger(session: Session, *, account_id: int, limit: int = 1000) -> list[dict]:
    account = session.get(Account, account_id)
    if account is None:
        raise ValueError("الحساب غير موجود")
    rows = session.execute(
        select(JournalEntry, JournalLine)
        .join(JournalLine, JournalLine.entry_id == JournalEntry.id)
        .where(JournalLine.account_id == account_id, JournalEntry.status == "posted")
        .order_by(JournalEntry.entry_date.asc(), JournalEntry.id.asc())
        .limit(max(1, min(int(limit), 5000)))
    ).all()
    running = Decimal("0.00")
    result = []
    for entry, line in rows:
        running += line.debit - line.credit
        result.append({
            "date": entry.entry_date, "number": entry.number,
            "description": line.description or entry.description,
            "debit": line.debit, "credit": line.credit, "balance": money(running),
        })
    return result
