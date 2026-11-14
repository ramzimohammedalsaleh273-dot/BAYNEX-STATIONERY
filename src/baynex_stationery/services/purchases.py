"""Supplier purchasing workflow with atomic stock receipt posting."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from baynex_stationery.db.models import (
    Product, Purchase, PurchaseItem, PurchasePayment, Supplier, Warehouse,
)
from baynex_stationery.domain.pricing import money
from baynex_stationery.services.inventory import get_stock_balance, record_stock_movement

CENT = Decimal("0.01")
QTY = Decimal("0.001")
PAYMENT_METHODS = {"cash", "card", "transfer"}


def _amount(value, label: str, places: Decimal, *, minimum: Decimal = Decimal(0)) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} غير صالح") from exc
    if not result.is_finite() or result < minimum or result != result.quantize(places):
        raise ValueError(f"{label} يجب أن يكون غير سالب وبدقة مسموحة")
    return result


def create_supplier(
    session: Session, *, code: str, name: str, phone: str | None = None,
    address: str | None = None, tax_number: str | None = None, notes: str | None = None,
) -> Supplier:
    clean_code, clean_name = code.strip().upper(), name.strip()
    if not clean_code or len(clean_code) > 40:
        raise ValueError("رمز المورد مطلوب ولا يتجاوز 40 حرفاً")
    if not clean_name or len(clean_name) > 180:
        raise ValueError("اسم المورد مطلوب ولا يتجاوز 180 حرفاً")
    supplier = Supplier(
        code=clean_code, name=clean_name, phone=phone.strip() if phone else None,
        address=address.strip() if address else None,
        tax_number=tax_number.strip() if tax_number else None,
        notes=notes.strip() if notes else None,
    )
    session.add(supplier)
    session.flush()
    return supplier


def list_suppliers(session: Session, *, search: str | None = None, include_inactive: bool = False) -> list[Supplier]:
    statement = select(Supplier).order_by(Supplier.name.asc())
    if not include_inactive:
        statement = statement.where(Supplier.is_active.is_(True))
    if search and search.strip():
        term = f"%{search.strip()}%"
        statement = statement.where(Supplier.name.ilike(term) | Supplier.code.ilike(term) | Supplier.phone.ilike(term))
    return list(session.scalars(statement))


def create_purchase(
    session: Session, *, number: str, supplier_id: int, warehouse_id: int,
    lines: list[dict], paid_amount: Decimal | str | int = Decimal(0),
    payment_method: str = "cash", supplier_invoice_number: str | None = None,
    notes: str | None = None, invoice_date: datetime | None = None,
) -> Purchase:
    clean_number = number.strip()
    if not clean_number or len(clean_number) > 40:
        raise ValueError("رقم فاتورة الشراء مطلوب ولا يتجاوز 40 حرفاً")
    supplier = session.get(Supplier, supplier_id)
    warehouse = session.get(Warehouse, warehouse_id)
    if supplier is None or not supplier.is_active:
        raise ValueError("المورد غير موجود أو غير نشط")
    if warehouse is None or not warehouse.is_active:
        raise ValueError("المستودع غير موجود أو غير نشط")
    if not lines:
        raise ValueError("لا يمكن حفظ فاتورة شراء دون أصناف")
    if payment_method not in PAYMENT_METHODS:
        raise ValueError("طريقة السداد غير معروفة")
    subtotal = Decimal("0.00")
    items: list[PurchaseItem] = []
    seen: set[int] = set()
    for index, row in enumerate(lines, 1):
        product_id = int(row["product_id"])
        if product_id in seen:
            raise ValueError("اجمع كميات الصنف الواحد في سطر واحد")
        seen.add(product_id)
        product = session.scalar(select(Product).options(joinedload(Product.unit_record)).where(Product.id == product_id))
        if product is None or not product.is_active:
            raise ValueError(f"الصنف في السطر {index} غير موجود أو غير نشط")
        quantity = _amount(row.get("quantity"), f"كمية السطر {index}", QTY, minimum=QTY)
        unit_cost = _amount(row.get("unit_cost", product.cost_price), f"تكلفة السطر {index}", CENT)
        discount = _amount(row.get("discount", 0), f"خصم السطر {index}", CENT)
        gross = money(quantity * unit_cost)
        if discount > gross:
            raise ValueError(f"خصم السطر {index} أكبر من قيمته")
        tax_rate = _amount(row.get("tax_rate", 0), f"ضريبة السطر {index}", Decimal("0.0001"))
        if tax_rate > 1:
            raise ValueError("نسبة الضريبة لا تتجاوز 100%")
        tax = money((gross - discount) * tax_rate)
        total = money(gross - discount + tax)
        subtotal += gross
        items.append(PurchaseItem(
            product_id=product.id, product_name=product.name, product_sku=product.sku,
            unit_name=product.unit_record.symbol if product.unit_record else product.unit,
            quantity=quantity, unit_cost=unit_cost, discount=discount,
            tax_amount=tax, line_total=total,
        ))
    invoice_discount = _amount(0, "خصم الفاتورة", CENT)
    tax_total = sum((item.tax_amount for item in items), Decimal("0.00"))
    total = money(sum((item.line_total for item in items), Decimal("0.00")) - invoice_discount)
    paid = _amount(paid_amount, "المبلغ المدفوع", CENT)
    if paid > total:
        raise ValueError("المبلغ المدفوع لا يجوز أن يتجاوز إجمالي الفاتورة")
    purchase = Purchase(
        number=clean_number, supplier_id=supplier_id, warehouse_id=warehouse_id,
        invoice_date=invoice_date or datetime.now(UTC),
        supplier_invoice_number=supplier_invoice_number.strip() if supplier_invoice_number else None,
        subtotal=money(subtotal), discount=invoice_discount, tax_amount=money(tax_total),
        total=total, paid_amount=paid, notes=notes.strip() if notes else None,
    )
    purchase.items.extend(items)
    if paid:
        purchase.payments.append(PurchasePayment(amount=paid, method=payment_method))
    session.add(purchase)
    session.flush()
    return purchase


def post_purchase(session: Session, *, purchase_id: int) -> Purchase:
    purchase = session.scalar(
        select(Purchase).options(joinedload(Purchase.items), joinedload(Purchase.payments))
        .where(Purchase.id == purchase_id).with_for_update()
    )
    if purchase is None or purchase.status != "draft":
        raise ValueError("فاتورة الشراء غير موجودة أو سبق ترحيلها")
    if not purchase.items:
        raise ValueError("فاتورة الشراء لا تحتوي على أصناف")
    for item in purchase.items:
        product = session.scalar(select(Product).where(Product.id == item.product_id).with_for_update())
        if product is None or not product.is_active:
            raise ValueError("أحد أصناف فاتورة الشراء غير موجود أو غير نشط")
        old_qty = get_stock_balance(session, product.id)
        new_qty = old_qty + item.quantity
        if new_qty > 0:
            product.cost_price = money(((old_qty * product.cost_price) + (item.quantity * item.unit_cost)) / new_qty)
        record_stock_movement(
            session, product_id=item.product_id, warehouse_id=purchase.warehouse_id,
            quantity_delta=item.quantity, movement_type="receipt",
            note=f"فاتورة شراء {purchase.number}",
            reference_type="purchase", reference_id=purchase.id,
        )
    purchase.status = "posted"
    purchase.posted_at = datetime.now(UTC)
    session.flush()
    return purchase


def list_purchases(
    session: Session, *, supplier_id: int | None = None, status: str | None = None, limit: int = 500,
) -> list[Purchase]:
    statement = select(Purchase).options(joinedload(Purchase.supplier), joinedload(Purchase.items)).order_by(
        Purchase.invoice_date.desc(), Purchase.id.desc()
    ).limit(max(1, min(int(limit), 5000)))
    if supplier_id is not None:
        statement = statement.where(Purchase.supplier_id == supplier_id)
    if status is not None:
        statement = statement.where(Purchase.status == status)
    return list(session.scalars(statement).unique())
