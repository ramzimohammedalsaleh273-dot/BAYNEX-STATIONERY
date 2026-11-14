"""Automatic general-ledger postings for sales and supplier invoices.

These entries use clearly named clearing/control accounts. They do not pretend
that a clearing account is a physical cashbox or bank account.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from baynex_stationery.db.models import Account, JournalEntry
from baynex_stationery.services.accounting import create_account, create_journal_entry, post_journal_entry

CENT = Decimal("0.01")


def _account(session: Session, *, code: str, name: str, account_type: str) -> Account:
    account = session.scalar(select(Account).where(Account.code == code))
    if account is not None:
        if account.account_type != account_type or not account.is_active:
            raise ValueError(f"حساب الربط المحاسبي {code} غير متاح أو نوعه غير صحيح")
        return account
    return create_account(session, code=code, name=name, account_type=account_type)


def _post_once(
    session: Session, *, source_type: str, source_id: int, number: str,
    description: str, entry_date, lines: list[dict],
) -> JournalEntry:
    existing = session.scalar(
        select(JournalEntry).where(
            JournalEntry.source_type == source_type,
            JournalEntry.source_id == source_id,
        )
    )
    if existing is not None:
        if existing.status != "posted":
            raise ValueError("يوجد قيد آلي سابق غير مرحل للمستند")
        return existing
    entry = create_journal_entry(
        session, number=number, description=description, entry_date=entry_date,
        source_type=source_type, source_id=source_id, lines=lines,
    )
    return post_journal_entry(session, entry_id=entry.id)


def post_sales_invoice_journal(session: Session, sale) -> JournalEntry:
    """Debit payment/receivable clearing and credit revenue/tax control."""
    total = Decimal(sale.total).quantize(CENT)
    tax = Decimal(sale.tax_amount).quantize(CENT)
    paid = Decimal(sale.paid_amount).quantize(CENT)
    receivable = total - paid
    revenue = total - tax
    if total <= 0 or tax < 0 or tax > total or paid < 0 or paid > total:
        raise ValueError("قيم فاتورة المبيعات لا تسمح بإنشاء قيد محاسبي متوازن")

    lines: list[dict] = []
    if paid:
        clearing = _account(
            session, code="1090", name="مدفوعات المبيعات تحت التسوية",
            account_type="asset",
        )
        lines.append({"account_id": clearing.id, "debit": paid})
    if receivable:
        ar = _account(session, code="1100", name="العملاء وأوراق القبض", account_type="asset")
        lines.append({"account_id": ar.id, "debit": receivable})
    if revenue:
        sales = _account(session, code="4100", name="إيرادات المبيعات", account_type="revenue")
        lines.append({"account_id": sales.id, "credit": revenue})
    if tax:
        tax_due = _account(session, code="2300", name="ضريبة مخرجات مستحقة", account_type="liability")
        lines.append({"account_id": tax_due.id, "credit": tax})
    return _post_once(
        session, source_type="sale", source_id=sale.id,
        number=f"AUTO-SALE-{sale.id}", description=f"قيد فاتورة المبيعات {sale.number}",
        entry_date=sale.invoice_date, lines=lines,
    )


def post_purchase_invoice_journal(session: Session, purchase) -> JournalEntry:
    """Debit inventory/input-tax and credit payment-clearing/supplier control."""
    total = Decimal(purchase.total).quantize(CENT)
    tax = Decimal(purchase.tax_amount).quantize(CENT)
    paid = Decimal(purchase.paid_amount).quantize(CENT)
    payable = total - paid
    inventory_cost = total - tax
    if total <= 0 or tax < 0 or tax > total or paid < 0 or paid > total:
        raise ValueError("قيم فاتورة المشتريات لا تسمح بإنشاء قيد محاسبي متوازن")

    lines: list[dict] = []
    if inventory_cost:
        inventory = _account(session, code="1200", name="مخزون البضاعة", account_type="asset")
        lines.append({"account_id": inventory.id, "debit": inventory_cost})
    if tax:
        input_tax = _account(session, code="1300", name="ضريبة مدخلات قابلة للاسترداد", account_type="asset")
        lines.append({"account_id": input_tax.id, "debit": tax})
    if paid:
        clearing = _account(
            session, code="2090", name="مدفوعات المشتريات تحت التسوية",
            account_type="liability",
        )
        lines.append({"account_id": clearing.id, "credit": paid})
    if payable:
        suppliers = _account(session, code="2100", name="الموردون", account_type="liability")
        lines.append({"account_id": suppliers.id, "credit": payable})
    return _post_once(
        session, source_type="purchase", source_id=purchase.id,
        number=f"AUTO-PUR-{purchase.id}", description=f"قيد فاتورة المشتريات {purchase.number}",
        entry_date=purchase.invoice_date, lines=lines,
    )
