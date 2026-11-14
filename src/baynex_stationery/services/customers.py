"""Customer master-data operations and searchable customer listing."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from baynex_stationery.db.models import Customer


def create_customer(
    session: Session, *, code: str, name: str, phone: str | None = None,
    address: str | None = None, tax_number: str | None = None, notes: str | None = None,
) -> Customer:
    clean_code, clean_name = code.strip().upper(), name.strip()
    if not clean_code or len(clean_code) > 40:
        raise ValueError("رمز العميل مطلوب ولا يتجاوز 40 حرفاً")
    if not clean_name or len(clean_name) > 180:
        raise ValueError("اسم العميل مطلوب ولا يتجاوز 180 حرفاً")
    customer = Customer(
        code=clean_code, name=clean_name, phone=phone.strip() if phone else None,
        address=address.strip() if address else None,
        tax_number=tax_number.strip() if tax_number else None,
        notes=notes.strip() if notes else None,
    )
    session.add(customer)
    session.flush()
    return customer


def list_customers(
    session: Session, *, search: str | None = None, include_inactive: bool = False,
) -> list[Customer]:
    statement = select(Customer).order_by(Customer.name.asc())
    if not include_inactive:
        statement = statement.where(Customer.is_active.is_(True))
    if search and search.strip():
        term = f"%{search.strip()}%"
        statement = statement.where(
            Customer.name.ilike(term) | Customer.code.ilike(term) | Customer.phone.ilike(term)
        )
    return list(session.scalars(statement))
