"""Party subsidiary ledgers sourced only from posted double-entry journals."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from baynex_stationery.db.models import JournalEntry, JournalLine


def _statement(session: Session, *, party_column, party_id: int, credit_nature: bool, limit: int):
    rows = session.execute(
        select(JournalEntry, JournalLine)
        .join(JournalLine, JournalLine.entry_id == JournalEntry.id)
        .where(party_column == party_id, JournalEntry.status == "posted")
        .order_by(JournalEntry.entry_date.asc(), JournalEntry.id.asc())
        .limit(max(1, min(int(limit), 5000)))
    ).all()
    running = Decimal("0.00")
    result = []
    for entry, line in rows:
        movement = line.credit - line.debit if credit_nature else line.debit - line.credit
        running += movement
        result.append({
            "date": entry.entry_date, "number": entry.number,
            "description": line.description or entry.description,
            "debit": line.debit, "credit": line.credit, "balance": running,
            "source_type": entry.source_type, "source_id": entry.source_id,
        })
    return result


def customer_statement(session: Session, *, customer_id: int, limit: int = 1000) -> list[dict]:
    from baynex_stationery.db.models import Customer
    if session.get(Customer, customer_id) is None:
        raise ValueError("العميل غير موجود")
    return _statement(
        session, party_column=JournalLine.customer_id, party_id=customer_id,
        credit_nature=False, limit=limit,
    )


def supplier_statement(session: Session, *, supplier_id: int, limit: int = 1000) -> list[dict]:
    from baynex_stationery.db.models import Supplier
    if session.get(Supplier, supplier_id) is None:
        raise ValueError("المورد غير موجود")
    return _statement(
        session, party_column=JournalLine.supplier_id, party_id=supplier_id,
        credit_nature=True, limit=limit,
    )
