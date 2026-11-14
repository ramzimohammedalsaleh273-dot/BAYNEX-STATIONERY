"""Transactional sales invoices backed by the immutable stock ledger."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from baynex_stationery.db.models import Payment, Product, Sale, SaleItem, Warehouse
from baynex_stationery.domain.pricing import money
from baynex_stationery.services.document_posting import post_sales_invoice_journal
from baynex_stationery.services.inventory import get_stock_balance, record_stock_movement

CENT = Decimal("0.01")
QTY = Decimal("0.001")
PAYMENT_METHODS = {"cash", "card", "transfer", "credit"}


def _decimal(value, label: str, *, places: Decimal, minimum: Decimal = Decimal(0)) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} غير صالح") from exc
    if not result.is_finite() or result < minimum:
        raise ValueError(f"{label} يجب أن يكون رقماً محدوداً وغير سالب")
    if result != result.quantize(places):
        precision = "ثلاث خانات عشرية" if places == QTY else "خانتين عشريتين"
        raise ValueError(f"{label} يقبل حتى {precision}")
    return result


def create_sale(
    session: Session,
    *,
    number: str,
    warehouse_id: int,
    lines: list[dict],
    customer_name: str = "عميل نقدي",
    customer_phone: str | None = None,
    payment_method: str = "cash",
    paid_amount: Decimal | str | int = Decimal(0),
    discount: Decimal | str | int = Decimal(0),
    tax_rate: Decimal | str | int = Decimal(0),
    notes: str | None = None,
    invoice_date: datetime | None = None,
) -> Sale:
    """Create a draft invoice; no stock or cash movement occurs until posting."""
    clean_number = number.strip()
    clean_customer = customer_name.strip()
    if not clean_number or len(clean_number) > 40:
        raise ValueError("رقم الفاتورة مطلوب ولا يتجاوز 40 حرفاً")
    if not clean_customer or len(clean_customer) > 160:
        raise ValueError("اسم العميل مطلوب ولا يتجاوز 160 حرفاً")
    if payment_method not in PAYMENT_METHODS:
        raise ValueError("طريقة السداد غير معروفة")
    warehouse = session.get(Warehouse, warehouse_id)
    if warehouse is None or not warehouse.is_active:
        raise ValueError("المستودع غير موجود أو غير نشط")
    if not lines:
        raise ValueError("لا يمكن حفظ فاتورة دون صنف واحد على الأقل")

    subtotal = Decimal("0.00")
    item_rows: list[SaleItem] = []
    seen_products: set[int] = set()
    for index, line in enumerate(lines, start=1):
        product_id = int(line["product_id"])
        if product_id in seen_products:
            raise ValueError("اجمع كميات الصنف الواحد في سطر واحد داخل الفاتورة")
        seen_products.add(product_id)
        product = session.scalar(
            select(Product).options(joinedload(Product.unit_record))
            .where(Product.id == product_id)
        )
        if product is None or not product.is_active:
            raise ValueError(f"الصنف في السطر {index} غير موجود أو غير نشط")
        quantity = _decimal(line.get("quantity"), f"كمية السطر {index}", places=QTY, minimum=QTY)
        unit_price = _decimal(
            line.get("unit_price", product.sale_price),
            f"سعر السطر {index}", places=CENT,
        )
        line_discount = _decimal(
            line.get("discount", 0), f"خصم السطر {index}", places=CENT,
        )
        gross = money(quantity * unit_price)
        if line_discount > gross:
            raise ValueError(f"خصم السطر {index} أكبر من قيمة السطر")
        net = gross - line_discount
        line_tax_rate = _decimal(
            line.get("tax_rate", tax_rate), f"ضريبة السطر {index}",
            places=Decimal("0.0001"),
        )
        if line_tax_rate > 1:
            raise ValueError(f"نسبة الضريبة في السطر {index} يجب ألا تتجاوز 100%")
        tax_amount = money(net * line_tax_rate)
        total = money(net + tax_amount)
        subtotal += gross
        item_rows.append(SaleItem(
            product_id=product.id,
            product_name=product.name,
            product_sku=product.sku,
            unit_name=product.unit_record.symbol if product.unit_record else product.unit,
            quantity=quantity,
            unit_price=unit_price,
            discount=line_discount,
            tax_amount=tax_amount,
            line_total=total,
        ))

    invoice_discount = _decimal(discount, "خصم الفاتورة", places=CENT)
    line_discount_total = sum((item.discount for item in item_rows), Decimal("0.00"))
    if invoice_discount > subtotal - line_discount_total:
        raise ValueError("خصم الفاتورة أكبر من صافي تفاصيل الأصناف")
    tax_total = sum((item.tax_amount for item in item_rows), Decimal("0.00"))
    total = money(sum((item.line_total for item in item_rows), Decimal("0.00")) - invoice_discount)
    paid = _decimal(paid_amount, "المبلغ المدفوع", places=CENT)
    if paid > total:
        raise ValueError("المبلغ المدفوع لا يجوز أن يتجاوز إجمالي الفاتورة")

    sale = Sale(
        number=clean_number,
        status="draft",
        customer_name=clean_customer,
        customer_phone=customer_phone.strip() if customer_phone else None,
        invoice_date=invoice_date or datetime.now(UTC),
        payment_method=payment_method,
        paid_amount=paid,
        notes=notes.strip() if notes else None,
        subtotal=money(subtotal),
        discount=money(invoice_discount + line_discount_total),
        tax_amount=money(tax_total),
        total=total,
        warehouse_id=warehouse_id,
    )
    sale.items.extend(item_rows)
    session.add(sale)
    session.flush()
    return sale


def _post_draft(session: Session, sale_id: int) -> Sale:
    sale = session.scalar(
        select(Sale).options(joinedload(Sale.items))
        .where(Sale.id == sale_id).with_for_update()
    )
    if sale is None:
        raise ValueError("فاتورة المبيعات غير موجودة")
    if sale.status != "draft":
        raise ValueError("الفاتورة ليست مسودة أو سبق ترحيلها")
    if not sale.items:
        raise ValueError("لا يمكن ترحيل فاتورة فارغة")
    required: dict[int, Decimal] = {}
    for item in sale.items:
        required[item.product_id] = required.get(item.product_id, Decimal(0)) + item.quantity
    for product_id, quantity in required.items():
        balance = get_stock_balance(session, product_id, sale.warehouse_id)
        if balance < quantity:
            product = session.get(Product, product_id)
            raise ValueError(f"الرصيد غير كافٍ للصنف: {product.name if product else product_id}")
    for item in sale.items:
        record_stock_movement(
            session,
            product_id=item.product_id,
            warehouse_id=sale.warehouse_id,
            quantity_delta=-item.quantity,
            movement_type="sale",
            note=f"فاتورة مبيعات {sale.number}",
            reference_type="sale",
            reference_id=sale.id,
        )
    if sale.paid_amount > 0:
        session.add(Payment(
            sale_id=sale.id,
            amount=sale.paid_amount,
            method=sale.payment_method,
        ))
    post_sales_invoice_journal(session, sale)
    sale.status = "posted"
    session.flush()
    return sale


def post_sale(
    session: Session,
    *,
    sale_id: int | None = None,
    number: str | None = None,
    items: list[dict] | None = None,
    discount: Decimal = Decimal(0),
    tax_rate: Decimal = Decimal(0),
    payment_method: str = "cash",
    paid_amount: Decimal | None = None,
    warehouse_id: int | None = None,
) -> Sale:
    """Post a draft by ID; legacy direct-post arguments remain supported."""
    if sale_id is not None:
        return _post_draft(session, sale_id)
    if number is None or items is None:
        raise ValueError("حدد رقم الفاتورة والأصناف أو رقم مسودة موجودة")
    warehouse = session.get(Warehouse, warehouse_id) if warehouse_id is not None else None
    if warehouse_id is None:
        from baynex_stationery.services.inventory import ensure_default_warehouse
        warehouse = ensure_default_warehouse(session)
    if warehouse is None or not warehouse.is_active:
        raise ValueError("المستودع غير موجود أو غير نشط")
    lines = [
        {"product_id": row["product_id"], "quantity": row["quantity"]}
        for row in items
    ]
    required: dict[int, Decimal] = {}
    for line in lines:
        product_id = int(line["product_id"])
        quantity = _decimal(line["quantity"], "الكمية", places=QTY, minimum=QTY)
        required[product_id] = required.get(product_id, Decimal(0)) + quantity
    for product_id, quantity in required.items():
        if get_stock_balance(session, product_id, warehouse.id) < quantity:
            product = session.get(Product, product_id)
            raise ValueError(f"الرصيد غير كافٍ للصنف: {product.name if product else product_id}")
    draft = create_sale(
        session, number=number, warehouse_id=warehouse.id, lines=lines,
        payment_method=payment_method, discount=discount, tax_rate=tax_rate,
        paid_amount=Decimal(0),
    )
    draft.paid_amount = draft.total if paid_amount is None else _decimal(
        paid_amount, "المبلغ المدفوع", places=CENT
    )
    if draft.paid_amount > draft.total:
        raise ValueError("المبلغ المدفوع يجب ألا يتجاوز إجمالي الفاتورة")
    session.flush()
    return _post_draft(session, draft.id)


def list_sales(
    session: Session, *, search: str | None = None, include_drafts: bool = True,
) -> list[Sale]:
    statement = select(Sale).options(joinedload(Sale.items)).order_by(
        Sale.invoice_date.desc(), Sale.id.desc()
    )
    if not include_drafts:
        statement = statement.where(Sale.status == "posted")
    if search and search.strip():
        term = f"%{search.strip()}%"
        statement = statement.where(
            Sale.number.ilike(term) | Sale.customer_name.ilike(term)
        )
    return list(session.scalars(statement).unique())
