"""Transactional sale posting. The caller owns the SQLAlchemy transaction."""
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from baynex_stationery.db.models import Payment, Product, Sale, SaleItem, Warehouse
from baynex_stationery.services.inventory import (
    ensure_default_warehouse,
    get_stock_balance,
    record_stock_movement,
)
from baynex_stationery.domain.pricing import invoice_total, line_total, money


def post_sale(
    session: Session,
    *,
    number: str,
    items: list[dict],
    discount: Decimal = Decimal(0),
    tax_rate: Decimal = Decimal(0),
    payment_method: str = "cash",
    paid_amount: Decimal | None = None,
    warehouse_id: int | None = None,
) -> Sale:
    """Post a sale, decrement stock and record immutable movement/payment rows."""
    if not number.strip():
        raise ValueError("رقم الفاتورة مطلوب")
    if not items:
        raise ValueError("الفاتورة يجب أن تحتوي على صنف واحد على الأقل")

    warehouse = session.get(Warehouse, warehouse_id) if warehouse_id is not None else ensure_default_warehouse(session)
    if warehouse is None or not warehouse.is_active:
        raise ValueError("المستودع غير موجود أو غير نشط")
    warehouse_id = warehouse.id

    normalized = []
    required: dict[int, Decimal] = defaultdict(lambda: Decimal(0))
    subtotal = Decimal(0)
    for row in items:
        product_id = int(row["product_id"])
        quantity = Decimal(str(row["quantity"]))
        if quantity <= 0:
            raise ValueError("الكمية يجب أن تكون أكبر من صفر")
        required[product_id] += quantity
        normalized.append((product_id, quantity))

    products = {
        product.id: product
        for product in session.scalars(
            select(Product).where(Product.id.in_(required.keys())).with_for_update()
        )
    }
    if len(products) != len(required):
        raise ValueError("يوجد صنف غير موجود في قاعدة البيانات")

    for product_id, quantity in required.items():
        product = products[product_id]
        if not product.is_active:
            raise ValueError(f"الصنف غير نشط: {product.name}")
        if get_stock_balance(session, product_id, warehouse_id) < quantity:
            raise ValueError(f"الرصيد غير كافٍ للصنف: {product.name}")

    sale_lines = []
    for product_id, quantity in normalized:
        product = products[product_id]
        amount = line_total(product.sale_price, quantity)
        subtotal += amount
        sale_lines.append((product, quantity, amount))

    subtotal = money(subtotal)
    total = invoice_total(subtotal, discount, tax_rate)
    discount_value = money(discount)
    tax_value = money(total - (subtotal - discount_value))

    paid = total if paid_amount is None else money(paid_amount)
    if paid < 0 or paid > total:
        raise ValueError("المبلغ المدفوع يجب ألا يكون سالباً أو أكبر من إجمالي الفاتورة")
    if not payment_method.strip():
        raise ValueError("طريقة الدفع مطلوبة")

    sale = Sale(
        number=number.strip(),
        status="posted",
        subtotal=subtotal,
        discount=discount_value,
        tax_amount=tax_value,
        total=total,
        warehouse_id=warehouse_id,
    )
    session.add(sale)
    session.flush()

    for product, quantity, amount in sale_lines:
        session.add(
            SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                product_name=product.name,
                quantity=quantity,
                unit_price=product.sale_price,
                line_total=amount,
            )
        )
        record_stock_movement(
            session, product_id=product.id, warehouse_id=warehouse_id,
            quantity_delta=-quantity, movement_type="sale",
            reference_type="sale", reference_id=sale.id,
            note=f"فاتورة {sale.number}",
        )

    if paid:
        session.add(
            Payment(
                sale_id=sale.id,
                amount=paid,
                method=payment_method.strip(),
            )
        )
    session.flush()
    return sale
