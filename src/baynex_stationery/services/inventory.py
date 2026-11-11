"""Warehouse-aware inventory ledger and controlled stock documents.

All functions flush but never commit: callers own the transaction boundary.
Stock balances are derived from posted signed movements; Product.stock_quantity
is maintained only as a compatibility aggregate for older screens and code.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from baynex_stationery.db.models import (
    InventoryCount,
    InventoryCountLine,
    InventoryTransfer,
    InventoryTransferLine,
    Product,
    StockMovement,
    Warehouse,
)

ZERO = Decimal("0.000")
ALLOWED_MOVEMENT_TYPES = {
    "opening", "receipt", "issue", "sale", "transfer_in", "transfer_out",
    "adjustment_in", "adjustment_out", "count_in", "count_out",
}


def _quantity(value: Decimal | str | int, label: str = "الكمية", *, allow_zero: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} غير صالحة") from exc
    if not result.is_finite():
        raise ValueError(f"{label} يجب أن تكون رقماً محدوداً")
    if result < 0 or (not allow_zero and result == 0):
        raise ValueError(f"{label} يجب أن تكون {'غير سالبة' if allow_zero else 'أكبر من صفر'}")
    if result != result.quantize(Decimal("0.001")):
        raise ValueError(f"{label} تقبل حتى ثلاث خانات عشرية")
    return result.quantize(Decimal("0.001"))


def ensure_default_warehouse(session: Session) -> Warehouse:
    warehouse = session.scalar(select(Warehouse).where(Warehouse.is_default.is_(True)))
    if warehouse is None:
        warehouse = session.scalar(select(Warehouse).where(Warehouse.code == "MAIN"))
    if warehouse is None:
        warehouse = Warehouse(code="MAIN", name="المستودع الرئيسي", is_default=True, is_active=True)
        session.add(warehouse)
        session.flush()
    elif not warehouse.is_default:
        warehouse.is_default = True
        session.flush()
    return warehouse


def create_warehouse(session: Session, *, code: str, name: str, is_default: bool = False) -> Warehouse:
    clean_code, clean_name = code.strip().upper(), name.strip()
    if not clean_code or len(clean_code) > 32:
        raise ValueError("رمز المستودع مطلوب ولا يتجاوز 32 حرفاً")
    if not clean_name or len(clean_name) > 120:
        raise ValueError("اسم المستودع مطلوب ولا يتجاوز 120 حرفاً")
    if is_default:
        for current in session.scalars(select(Warehouse).where(Warehouse.is_default.is_(True))):
            current.is_default = False
    warehouse = Warehouse(code=clean_code, name=clean_name, is_default=is_default, is_active=True)
    session.add(warehouse)
    session.flush()
    if is_default:
        warehouse.is_default = True
    return warehouse


def list_warehouses(session: Session, *, include_inactive: bool = False) -> list[Warehouse]:
    statement = select(Warehouse).order_by(Warehouse.is_default.desc(), Warehouse.name.asc())
    if not include_inactive:
        statement = statement.where(Warehouse.is_active.is_(True))
    return list(session.scalars(statement))


def set_warehouse_active(session: Session, warehouse_id: int, active: bool) -> Warehouse:
    warehouse = session.get(Warehouse, warehouse_id)
    if warehouse is None:
        raise ValueError("المستودع غير موجود")
    if not active:
        if warehouse.is_default:
            raise ValueError("لا يمكن إيقاف المستودع الافتراضي")
        nonzero = session.execute(
            select(StockMovement.product_id)
            .where(StockMovement.warehouse_id == warehouse_id)
            .group_by(StockMovement.product_id)
            .having(func.sum(StockMovement.quantity_delta) != 0)
            .limit(1)
        ).first()
        if nonzero is not None:
            raise ValueError("لا يمكن إيقاف مستودع لديه رصيد مخزون غير صفري")
    warehouse.is_active = bool(active)
    session.flush()
    return warehouse


def get_stock_balance(session: Session, product_id: int, warehouse_id: int | None = None) -> Decimal:
    statement = select(func.coalesce(func.sum(StockMovement.quantity_delta), 0)).where(
        StockMovement.product_id == product_id
    )
    if warehouse_id is not None:
        statement = statement.where(StockMovement.warehouse_id == warehouse_id)
    value = session.scalar(statement)
    return Decimal(str(value or 0)).quantize(Decimal("0.001"))


def list_stock_balances(
    session: Session, *, warehouse_id: int | None = None, search: str | None = None
) -> list[tuple[Product, Decimal]]:
    statement = select(Product).where(Product.is_active.is_(True)).order_by(Product.name.asc())
    if search and search.strip():
        term = f"%{search.strip()}%"
        statement = statement.where(
            Product.name.ilike(term) | Product.sku.ilike(term) | Product.barcode.ilike(term)
        )
    rows = []
    for product in session.scalars(statement):
        rows.append((product, get_stock_balance(session, product.id, warehouse_id)))
    return rows


def record_stock_movement(
    session: Session,
    *,
    product_id: int,
    warehouse_id: int,
    quantity_delta: Decimal | str | int,
    movement_type: str,
    note: str | None = None,
    reference_type: str = "manual",
    reference_id: int = 0,
    allow_negative: bool = False,
) -> StockMovement:
    if movement_type not in ALLOWED_MOVEMENT_TYPES:
        raise ValueError("نوع حركة المخزون غير معروف")
    try:
        delta = Decimal(str(quantity_delta))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("كمية الحركة غير صالحة") from exc
    if not delta.is_finite() or delta == 0 or delta != delta.quantize(Decimal("0.001")):
        raise ValueError("كمية الحركة يجب أن تكون محدودة وغير صفرية وبحد أقصى ثلاث خانات عشرية")
    positive_types = {"opening", "receipt", "transfer_in", "adjustment_in", "count_in"}
    negative_types = {"issue", "sale", "transfer_out", "adjustment_out", "count_out"}
    if movement_type in positive_types and delta <= 0:
        raise ValueError("هذا النوع من الحركة يتطلب كمية موجبة")
    if movement_type in negative_types and delta >= 0:
        raise ValueError("هذا النوع من الحركة يتطلب كمية سالبة")
    product = session.scalar(select(Product).where(Product.id == product_id).with_for_update())
    if product is None:
        raise ValueError("الصنف غير موجود")
    if not product.is_active:
        raise ValueError(f"الصنف غير نشط: {product.name}")
    warehouse = session.get(Warehouse, warehouse_id)
    if warehouse is None or not warehouse.is_active:
        raise ValueError("المستودع غير موجود أو غير نشط")
    current = get_stock_balance(session, product_id, warehouse_id)
    if delta < 0 and not allow_negative and current + delta < 0:
        raise ValueError(f"الرصيد غير كافٍ للصنف: {product.name} في المستودع المحدد")
    movement = StockMovement(
        product_id=product_id,
        warehouse_id=warehouse_id,
        movement_type=movement_type,
        quantity_delta=delta,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note.strip() or None if note else None,
    )
    session.add(movement)
    session.flush()
    product.stock_quantity = get_stock_balance(session, product_id)
    session.flush()
    return movement


def receive_stock(
    session: Session, *, product_id: int, warehouse_id: int, quantity: Decimal | str | int,
    note: str | None = None,
) -> StockMovement:
    amount = _quantity(quantity)
    return record_stock_movement(
        session, product_id=product_id, warehouse_id=warehouse_id,
        quantity_delta=amount, movement_type="receipt", note=note,
    )


def issue_stock(
    session: Session, *, product_id: int, warehouse_id: int, quantity: Decimal | str | int,
    note: str | None = None,
) -> StockMovement:
    amount = _quantity(quantity)
    return record_stock_movement(
        session, product_id=product_id, warehouse_id=warehouse_id,
        quantity_delta=-amount, movement_type="issue", note=note,
    )


def create_inventory_count(
    session: Session, *, number: str, warehouse_id: int, note: str | None = None
) -> InventoryCount:
    if not number.strip():
        raise ValueError("رقم الجرد مطلوب")
    warehouse = session.get(Warehouse, warehouse_id)
    if warehouse is None or not warehouse.is_active:
        raise ValueError("المستودع غير موجود أو غير نشط")
    count = InventoryCount(number=number.strip(), warehouse_id=warehouse_id, note=note)
    session.add(count)
    session.flush()
    products = session.scalars(select(Product).where(Product.is_active.is_(True)).order_by(Product.id))
    for product in products:
        book = get_stock_balance(session, product.id, warehouse_id)
        session.add(InventoryCountLine(
            count_id=count.id, product_id=product.id,
            book_quantity=book, counted_quantity=book, difference=ZERO,
        ))
    session.flush()
    return count


def set_inventory_count_line(
    session: Session, *, count_id: int, product_id: int, counted_quantity: Decimal | str | int
) -> InventoryCountLine:
    count = session.get(InventoryCount, count_id)
    if count is None or count.status != "draft":
        raise ValueError("جلسة الجرد غير موجودة أو ليست مسودة")
    line = session.scalar(select(InventoryCountLine).where(
        InventoryCountLine.count_id == count_id,
        InventoryCountLine.product_id == product_id,
    ))
    if line is None:
        raise ValueError("الصنف غير موجود ضمن جلسة الجرد")
    counted = _quantity(counted_quantity, "الكمية الفعلية", allow_zero=True)
    line.counted_quantity = counted
    line.difference = (counted - line.book_quantity).quantize(Decimal("0.001"))
    session.flush()
    return line


def post_inventory_count(session: Session, *, count_id: int) -> InventoryCount:
    count = session.scalar(select(InventoryCount).where(InventoryCount.id == count_id).with_for_update())
    if count is None or count.status != "draft":
        raise ValueError("جلسة الجرد غير موجودة أو سبق ترحيلها")
    lines = list(session.scalars(select(InventoryCountLine).where(
        InventoryCountLine.count_id == count_id
    ).order_by(InventoryCountLine.id)))
    for line in lines:
        current = get_stock_balance(session, line.product_id, count.warehouse_id)
        if current != line.book_quantity:
            raise ValueError("تغير رصيد أحد الأصناف بعد بدء الجرد؛ ألغِ الجلسة وأنشئ جرداً جديداً")
    for line in lines:
        if line.difference:
            record_stock_movement(
                session, product_id=line.product_id, warehouse_id=count.warehouse_id,
                quantity_delta=line.difference,
                movement_type="count_in" if line.difference > 0 else "count_out",
                note=f"تسوية جرد {count.number}",
                reference_type="inventory_count", reference_id=count.id,
            )
    count.status = "posted"
    count.posted_at = datetime.now(UTC)
    session.flush()
    return count


def create_inventory_transfer(
    session: Session, *, number: str, source_warehouse_id: int,
    destination_warehouse_id: int, lines: list[dict], note: str | None = None,
) -> InventoryTransfer:
    if not number.strip():
        raise ValueError("رقم التحويل مطلوب")
    if source_warehouse_id == destination_warehouse_id:
        raise ValueError("لا يمكن التحويل إلى المستودع نفسه")
    source = session.get(Warehouse, source_warehouse_id)
    destination = session.get(Warehouse, destination_warehouse_id)
    if not source or not source.is_active or not destination or not destination.is_active:
        raise ValueError("المستودع المصدر أو الوجهة غير موجود أو غير نشط")
    if not lines:
        raise ValueError("يجب إضافة صنف واحد على الأقل للتحويل")
    transfer = InventoryTransfer(
        number=number.strip(), source_warehouse_id=source_warehouse_id,
        destination_warehouse_id=destination_warehouse_id, note=note,
    )
    session.add(transfer)
    session.flush()
    seen: set[int] = set()
    for item in lines:
        product_id = int(item["product_id"])
        if product_id in seen:
            raise ValueError("لا تكرر الصنف نفسه في مستند التحويل")
        seen.add(product_id)
        quantity = _quantity(item["quantity"])
        session.add(InventoryTransferLine(
            transfer_id=transfer.id, product_id=product_id, quantity=quantity,
        ))
    session.flush()
    return transfer


def post_inventory_transfer(session: Session, *, transfer_id: int) -> InventoryTransfer:
    transfer = session.scalar(select(InventoryTransfer).where(
        InventoryTransfer.id == transfer_id
    ).with_for_update())
    if transfer is None or transfer.status != "draft":
        raise ValueError("مستند التحويل غير موجود أو سبق ترحيله")
    lines = list(session.scalars(select(InventoryTransferLine).where(
        InventoryTransferLine.transfer_id == transfer_id
    ).order_by(InventoryTransferLine.id)))
    if not lines:
        raise ValueError("مستند التحويل لا يحتوي على أصناف")
    for line in lines:
        available = get_stock_balance(session, line.product_id, transfer.source_warehouse_id)
        if available < line.quantity:
            product = session.get(Product, line.product_id)
            raise ValueError(f"الرصيد غير كافٍ للتحويل للصنف: {product.name if product else line.product_id}")
    for line in lines:
        record_stock_movement(
            session, product_id=line.product_id, warehouse_id=transfer.source_warehouse_id,
            quantity_delta=-line.quantity, movement_type="transfer_out",
            note=f"تحويل {transfer.number}", reference_type="inventory_transfer",
            reference_id=transfer.id,
        )
        record_stock_movement(
            session, product_id=line.product_id, warehouse_id=transfer.destination_warehouse_id,
            quantity_delta=line.quantity, movement_type="transfer_in",
            note=f"تحويل {transfer.number}", reference_type="inventory_transfer",
            reference_id=transfer.id,
        )
    transfer.status = "posted"
    transfer.posted_at = datetime.now(UTC)
    session.flush()
    return transfer


def list_stock_movements(
    session: Session, *, product_id: int | None = None, warehouse_id: int | None = None,
    limit: int = 500,
) -> list[StockMovement]:
    statement = select(StockMovement).order_by(
        StockMovement.created_at.desc(), StockMovement.id.desc()
    ).limit(max(1, min(int(limit), 5000)))
    if product_id is not None:
        statement = statement.where(StockMovement.product_id == product_id)
    if warehouse_id is not None:
        statement = statement.where(StockMovement.warehouse_id == warehouse_id)
    return list(session.scalars(statement))
