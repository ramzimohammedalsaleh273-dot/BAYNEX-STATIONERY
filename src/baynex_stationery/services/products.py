"""Validated product catalog operations."""
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from baynex_stationery.db.models import Category, Product, Unit
from baynex_stationery.domain.pricing import decimal_value, money


def _required_text(value: str, label: str, maximum: int) -> str:
    result = value.strip()
    if not result:
        raise ValueError(f"{label} مطلوب")
    if len(result) > maximum:
        raise ValueError(f"{label} لا يتجاوز {maximum} حرفاً")
    return result


def _non_negative(value: Decimal, label: str, places: str) -> Decimal:
    result = decimal_value(value, label)
    if result < 0:
        raise ValueError(f"{label} لا يمكن أن يكون سالباً")
    if result != result.quantize(Decimal(places)):
        scale = len(places.partition(".")[2])
        raise ValueError(f"{label} يقبل حتى {scale} خانات عشرية")
    return result


def list_products(
    session: Session,
    include_inactive: bool = False,
    *,
    search: str | None = None,
    category_id: int | None = None,
    low_stock_only: bool = False,
) -> list[Product]:
    statement = select(Product).options(joinedload(Product.category), joinedload(Product.unit_record))
    if not include_inactive:
        statement = statement.where(Product.is_active.is_(True))
    if search and search.strip():
        term = f"%{search.strip()}%"
        statement = statement.where(or_(Product.name.ilike(term), Product.sku.ilike(term), Product.barcode.ilike(term)))
    if category_id is not None:
        statement = statement.where(Product.category_id == category_id)
    if low_stock_only:
        statement = statement.where(Product.stock_quantity <= Product.minimum_stock)
    return list(session.scalars(statement.order_by(Product.name.asc())))


def get_product_by_barcode(session: Session, barcode: str) -> Product | None:
    code = barcode.strip()
    if not code:
        return None
    return session.scalar(
        select(Product).options(joinedload(Product.category), joinedload(Product.unit_record))
        .where(Product.barcode == code, Product.is_active.is_(True))
    )


def create_product(
    session: Session,
    *,
    sku: str,
    name: str,
    sale_price: Decimal,
    cost_price: Decimal = Decimal(0),
    opening_stock: Decimal = Decimal(0),
    barcode: str | None = None,
    unit: str = "قطعة",
    unit_id: int | None = None,
    category_id: int | None = None,
    minimum_stock: Decimal = Decimal(0),
    notes: str | None = None,
) -> Product:
    sku = _required_text(sku, "رمز الصنف", 64)
    name = _required_text(name, "اسم الصنف", 200)
    unit = _required_text(unit, "الوحدة", 32)
    sale_price = money(_non_negative(sale_price, "سعر البيع", "0.01"))
    cost_price = money(_non_negative(cost_price, "سعر التكلفة", "0.01"))
    opening_stock = _non_negative(opening_stock, "الرصيد الافتتاحي", "0.001")
    minimum_stock = _non_negative(minimum_stock, "حد إعادة الطلب", "0.001")
    barcode = _required_text(barcode, "الباركود", 64) if barcode and barcode.strip() else None
    if category_id is not None:
        category = session.get(Category, category_id)
        if category is None or not category.is_active:
            raise ValueError("التصنيف المحدد غير موجود أو غير نشط")
    if unit_id is not None:
        unit_record = session.get(Unit, unit_id)
        if unit_record is None or not unit_record.is_active:
            raise ValueError("الوحدة المحددة غير موجودة أو غير نشطة")
        unit = unit_record.symbol
    product = Product(
        sku=sku, name=name, sale_price=sale_price, cost_price=cost_price,
        stock_quantity=opening_stock, minimum_stock=minimum_stock,
        barcode=barcode, unit=unit, unit_id=unit_id, category_id=category_id,
        notes=notes.strip() or None if notes else None,
    )
    session.add(product)
    session.flush()
    return product


def update_product(session: Session, product_id: int, **changes) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise ValueError("الصنف غير موجود")
    allowed = {"sku", "name", "sale_price", "cost_price", "barcode", "unit", "unit_id", "category_id", "minimum_stock", "notes"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"حقول غير مسموح بتعديلها: {', '.join(sorted(unknown))}")
    if "sku" in changes:
        product.sku = _required_text(changes["sku"], "رمز الصنف", 64)
    if "name" in changes:
        product.name = _required_text(changes["name"], "اسم الصنف", 200)
    for field, label in (("sale_price", "سعر البيع"), ("cost_price", "سعر التكلفة")):
        if field in changes:
            product_value = money(_non_negative(changes[field], label, "0.01"))
            setattr(product, field, product_value)
    if "barcode" in changes:
        value = changes["barcode"]
        product.barcode = _required_text(value, "الباركود", 64) if value and value.strip() else None
    if "unit" in changes:
        product.unit = _required_text(changes["unit"], "الوحدة", 32)
    if "unit_id" in changes:
        unit_id = changes["unit_id"]
        unit_record = session.get(Unit, unit_id) if unit_id is not None else None
        if unit_id is not None and (unit_record is None or not unit_record.is_active):
            raise ValueError("الوحدة المحددة غير موجودة أو غير نشطة")
        product.unit_id = unit_id
        if unit_record:
            product.unit = unit_record.symbol
    if "category_id" in changes:
        category_id = changes["category_id"]
        category = session.get(Category, category_id) if category_id is not None else None
        if category_id is not None and (category is None or not category.is_active):
            raise ValueError("التصنيف المحدد غير موجود أو غير نشط")
        product.category_id = category_id
    if "minimum_stock" in changes:
        product.minimum_stock = _non_negative(changes["minimum_stock"], "حد إعادة الطلب", "0.001")
    if "notes" in changes:
        product.notes = changes["notes"].strip() or None if changes["notes"] else None
    session.flush()
    return product


def set_product_active(session: Session, product_id: int, active: bool) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise ValueError("الصنف غير موجود")
    product.is_active = bool(active)
    session.flush()
    return product
