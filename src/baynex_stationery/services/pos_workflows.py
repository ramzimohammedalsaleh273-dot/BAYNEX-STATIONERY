"""Point-of-sale workflows: persisted holds, linked returns and cashier audit."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from baynex_stationery.db.models import (
    CashierEvent,
    Payment,
    Sale,
    SaleReturn,
    SaleReturnItem,
)
from baynex_stationery.domain.pricing import money
from baynex_stationery.services.inventory import record_stock_movement

REFUND_METHODS = {"cash", "card", "transfer", "credit"}


def list_held_sales(session: Session) -> list[Sale]:
    return list(session.scalars(
        select(Sale).options(joinedload(Sale.items))
        .where(Sale.status == "held")
        .order_by(Sale.created_at.desc(), Sale.id.desc())
    ).unique())


def log_cashier_event(
    session: Session, *, action: str, reference_type: str,
    reference_id: int, reference_number: str,
    amount: Decimal = Decimal("0.00"), details: str | None = None,
) -> CashierEvent:
    if not action.strip() or not reference_type.strip() or not reference_number.strip():
        raise ValueError("بيانات سجل الكاشير غير مكتملة")
    event = CashierEvent(
        action=action.strip(), reference_type=reference_type.strip(),
        reference_id=reference_id, reference_number=reference_number.strip(),
        amount=money(Decimal(str(amount))), details=details,
    )
    session.add(event)
    session.flush()
    return event


def create_sale_return(
    session: Session, *, number: str, sale_id: int,
    lines: list[dict], refund_method: str = "cash",
    notes: str | None = None,
) -> SaleReturn:
    """Create a posted return, restock returned goods, and audit it atomically."""
    clean_number = number.strip()
    if not clean_number or len(clean_number) > 40:
        raise ValueError("رقم المرتجع مطلوب ولا يتجاوز 40 حرفاً")
    if refund_method not in REFUND_METHODS:
        raise ValueError("طريقة رد المبلغ غير معروفة")
    sale = session.scalar(
        select(Sale).options(joinedload(Sale.items))
        .where(Sale.id == sale_id).with_for_update()
    )
    if sale is None or sale.status != "posted":
        raise ValueError("لا يمكن إرجاع أصناف إلا من فاتورة مبيعات مرحلة")
    if not lines:
        raise ValueError("حدد صنفاً واحداً على الأقل للمرتجع")

    returned: dict[int, Decimal] = {}
    prior_rows = session.execute(
        select(SaleReturnItem.sale_item_id, func.coalesce(func.sum(SaleReturnItem.quantity), 0))
        .join(SaleReturn, SaleReturn.id == SaleReturnItem.sale_return_id)
        .where(SaleReturn.sale_id == sale_id, SaleReturn.status == "posted")
        .group_by(SaleReturnItem.sale_item_id)
    ).all()
    returned.update({int(item_id): Decimal(str(quantity)) for item_id, quantity in prior_rows})

    sale_items = {item.id: item for item in sale.items}
    result_lines: list[SaleReturnItem] = []
    total_refund = Decimal("0.00")
    seen: set[int] = set()
    for index, line in enumerate(lines, start=1):
        try:
            sale_item_id = int(line["sale_item_id"])
            quantity = Decimal(str(line["quantity"]))
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise ValueError(f"بيانات صنف المرتجع في السطر {index} غير صحيحة") from exc
        item = sale_items.get(sale_item_id)
        if item is None or sale_item_id in seen:
            raise ValueError(f"الصنف في السطر {index} لا يتبع فاتورة البيع المحددة أو مكرر")
        seen.add(sale_item_id)
        if not quantity.is_finite() or quantity <= 0 or quantity != quantity.quantize(Decimal("0.001")):
            raise ValueError("كمية المرتجع يجب أن تكون موجبة وبحد أقصى ثلاث خانات عشرية")
        remaining = item.quantity - returned.get(item.id, Decimal(0))
        if quantity > remaining:
            raise ValueError(
                f"الكمية المرتجعة تتجاوز المتبقي للصنف {item.product_name}: {remaining:.3f}"
            )
        unit_refund = item.line_total / item.quantity
        line_refund = money(unit_refund * quantity)
        total_refund += line_refund
        result_lines.append(SaleReturnItem(
            sale_item_id=item.id, product_id=item.product_id,
            quantity=quantity, unit_price=item.unit_price, line_total=line_refund,
        ))

    total_refund = money(total_refund)
    previous_refunds = session.scalar(
        select(func.coalesce(func.sum(-Payment.amount), 0)).where(
            Payment.sale_id == sale.id, Payment.amount < 0
        )
    )
    refundable_paid = max(Decimal("0.00"), sale.paid_amount - Decimal(str(previous_refunds or 0)))
    if total_refund > refundable_paid:
        raise ValueError(
            f"قيمة المرتجع {total_refund:.2f} تتجاوز المبلغ المحصل المتاح "
            f"لرده {refundable_paid:.2f}. لا يمكن رد مبالغ لم تُحصّل من العميل."
        )
    returned_doc = SaleReturn(
        number=clean_number, sale_id=sale.id, status="posted",
        refund_method=refund_method, refund_amount=total_refund,
        notes=notes.strip() if notes else None,
    )
    returned_doc.items.extend(result_lines)
    session.add(returned_doc)
    session.flush()
    session.add(Payment(
        sale_id=sale.id, amount=-total_refund,
        method=f"refund_{refund_method}",
    ))
    for item in result_lines:
        record_stock_movement(
            session, product_id=item.product_id, warehouse_id=sale.warehouse_id,
            quantity_delta=item.quantity, movement_type="adjustment_in",
            note=f"مرتجع مبيعات {clean_number} من الفاتورة {sale.number}",
            reference_type="sale_return", reference_id=returned_doc.id,
        )
    log_cashier_event(
        session, action="sale_return", reference_type="sale_return",
        reference_id=returned_doc.id, reference_number=clean_number,
        amount=total_refund, details=f"مرتجع مرتبط بفاتورة {sale.number}",
    )
    return returned_doc
