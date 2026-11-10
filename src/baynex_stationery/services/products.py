"""Product catalog services with normalized SKU and barcode handling."""
from __future__ import annotations

import re
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from baynex_stationery.db.models import Category, Product, ProductBarcode, UnitOfMeasure
from baynex_stationery.domain.pricing import decimal_value, money


def _text(value: str, label: str, limit: int) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{label} مطلوب")
    if len(cleaned) > limit:
        raise ValueError(f"{label} يجب ألا يتجاوز {limit} حرفاً")
    return cleaned

def _sku(value: str) -> str:
    value = _text(value, "رمز الصنف", 64)
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", value):
        raise ValueError("رمز الصنف يقبل الأحرف الإنجليزية والأرقام والشرطة والنقطة والشرطة السفلية فقط")
    return value.upper()

def _barcode(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip().upper()
    if len(value) < 3 or len(value) > 64 or not re.fullmatch(r"[A-Z0-9-]+", value):
        raise ValueError("الباركود غير صالح؛ استخدم أحرفاً وأرقاماً وشرطة فقط")
    return value

def _unit(session: Session, name: str) -> UnitOfMeasure:
    name = _text(name, "الوحدة", 32)
    row = session.scalar(select(UnitOfMeasure).where(func.lower(UnitOfMeasure.name) == name.casefold()))
    if row is None and name == "قطعة":
        row = UnitOfMeasure(code="PCS", name="قطعة", symbol="قطعة", decimal_places=0)
        session.add(row)
        session.flush()
    if row is None or not row.is_active:
        raise ValueError("الوحدة غير مسجلة أو غير نشطة؛ أضف الوحدة أولاً من إدارة الوحدات")
    return row

def _category(session: Session, category_id: int | None) -> Category | None:
    if category_id is None:
        return None
    row = session.get(Category, category_id)
    if row is None or not row.is_active:
        raise ValueError("التصنيف غير موجود أو غير نشط")
    return row

def _barcode_used(session: Session, code: str, except_product: int | None = None) -> bool:
    stmt = select(ProductBarcode.id).where(func.lower(ProductBarcode.code) == code.casefold())
    if except_product is not None:
        stmt = stmt.where(ProductBarcode.product_id != except_product)
    if session.scalar(stmt):
        return True
    stmt = select(Product.id).where(func.lower(Product.barcode) == code.casefold())
    if except_product is not None:
        stmt = stmt.where(Product.id != except_product)
    return session.scalar(stmt) is not None

def list_products(session: Session, include_inactive: bool = False, *,
                  search: str | None = None, category_id: int | None = None) -> list[Product]:
    stmt = select(Product).options(selectinload(Product.category), selectinload(Product.unit_record))
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        alt = select(ProductBarcode.id).where(
            ProductBarcode.product_id == Product.id, ProductBarcode.code.ilike(pattern)
        ).exists()
        stmt = stmt.where(or_(Product.name.ilike(pattern), Product.sku.ilike(pattern),
                              Product.barcode.ilike(pattern), alt))
    return list(session.scalars(stmt.order_by(Product.name.asc(), Product.id.asc())))

def create_product(session: Session, *, sku: str, name: str, sale_price: Decimal,
                   cost_price: Decimal = Decimal(0), opening_stock: Decimal = Decimal(0),
                   barcode: str | None = None, unit: str = "قطعة",
                   category_id: int | None = None, minimum_stock: Decimal = Decimal(0),
                   notes: str | None = None) -> Product:
    sku = _sku(sku)
    name = _text(name, "اسم الصنف", 200)
    if session.scalar(select(Product.id).where(func.lower(Product.sku) == sku.casefold())):
        raise ValueError("رمز الصنف مستخدم بالفعل")
    sale_price = money(decimal_value(sale_price, "سعر البيع"))
    cost_price = money(decimal_value(cost_price, "سعر التكلفة"))
    opening_stock = decimal_value(opening_stock, "الرصيد الافتتاحي")
    minimum_stock = decimal_value(minimum_stock, "الحد الأدنى للمخزون")
    if min(sale_price, cost_price, opening_stock, minimum_stock) < 0:
        raise ValueError("الأسعار والكميات لا يمكن أن تكون سالبة")
    unit_row = _unit(session, unit)
    quantity_step = Decimal(1).scaleb(-unit_row.decimal_places)
    for label, value in (("الرصيد الافتتاحي", opening_stock), ("الحد الأدنى للمخزون", minimum_stock)):
        if value != value.quantize(quantity_step):
            raise ValueError(f"{label} لا يقبل أكثر من {unit_row.decimal_places} خانات عشرية حسب الوحدة")
    code = _barcode(barcode)
    if code and _barcode_used(session, code):
        raise ValueError("الباركود مستخدم لصنف آخر")
    _category(session, category_id)
    row = Product(sku=sku, name=name, sale_price=sale_price, cost_price=cost_price,
                  stock_quantity=opening_stock, minimum_stock=minimum_stock, barcode=code,
                  unit=unit_row.name, unit_record=unit_row, category_id=category_id,
                  notes=notes.strip() if notes else None)
    session.add(row)
    session.flush()
    if code:
        session.add(ProductBarcode(product_id=row.id, code=code,
                                   barcode_type="primary", is_primary=True))
        session.flush()
    return row

def add_product_barcode(session: Session, product_id: int, code: str, *,
                        barcode_type: str = "internal") -> ProductBarcode:
    product = session.get(Product, product_id)
    if product is None or not product.is_active:
        raise ValueError("الصنف غير موجود أو غير نشط")
    code = _barcode(code)
    if code is None:
        raise ValueError("الباركود مطلوب")
    if _barcode_used(session, code):
        raise ValueError("الباركود مستخدم بالفعل")
    if barcode_type not in {"internal", "ean", "upc", "isbn", "other"}:
        raise ValueError("نوع الباركود غير مدعوم")
    row = ProductBarcode(product_id=product_id, code=code, barcode_type=barcode_type)
    session.add(row)
    session.flush()
    return row

def find_product_by_barcode(session: Session, code: str) -> Product | None:
    code = _barcode(code)
    if code is None:
        return None
    stmt = select(Product).outerjoin(ProductBarcode, ProductBarcode.product_id == Product.id).where(
        Product.is_active.is_(True),
        or_(func.lower(Product.barcode) == code.casefold(),
            func.lower(ProductBarcode.code) == code.casefold())
    ).options(selectinload(Product.category), selectinload(Product.unit_record))
    return session.scalar(stmt)

def update_product(session: Session, product_id: int, **changes) -> Product:
    row = session.get(Product, product_id)
    if row is None:
        raise ValueError("الصنف غير موجود")
    allowed = {"sku", "name", "sale_price", "cost_price", "unit", "category_id",
               "minimum_stock", "barcode", "notes"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"حقول غير مسموح بتعديلها: {', '.join(sorted(unknown))}")
    if "sku" in changes:
        sku = _sku(changes["sku"])
        stmt = select(Product.id).where(func.lower(Product.sku) == sku.casefold(), Product.id != product_id)
        if session.scalar(stmt):
            raise ValueError("رمز الصنف مستخدم بالفعل")
        row.sku = sku
    if "name" in changes:
        row.name = _text(changes["name"], "اسم الصنف", 200)
    for field, label in (("sale_price", "سعر البيع"), ("cost_price", "سعر التكلفة")):
        if field in changes:
            value = money(decimal_value(changes[field], label))
            if value < 0:
                raise ValueError(f"{label} لا يمكن أن يكون سالباً")
            setattr(row, field, value)
    if "minimum_stock" in changes:
        value = decimal_value(changes["minimum_stock"], "الحد الأدنى للمخزون")
        places = row.unit_record.decimal_places if row.unit_record else 3
        step = Decimal(1).scaleb(-places)
        if value < 0 or value != value.quantize(step):
            raise ValueError(f"الحد الأدنى للمخزون غير صالح للوحدة الحالية ({places} خانات عشرية)")
        row.minimum_stock = value
    if "unit" in changes:
        unit_row = _unit(session, changes["unit"])
        step = Decimal(1).scaleb(-unit_row.decimal_places)
        for label, quantity in (("الرصيد الحالي", row.stock_quantity), ("حد التنبيه", row.minimum_stock)):
            if quantity != quantity.quantize(step):
                raise ValueError(f"لا يمكن تغيير الوحدة؛ {label} لا يطابق دقة الوحدة الجديدة")
        row.unit = unit_row.name
        row.unit_record = unit_row
    if "category_id" in changes:
        _category(session, changes["category_id"])
        row.category_id = changes["category_id"]
    if "notes" in changes:
        row.notes = changes["notes"].strip() if changes["notes"] else None
    if "barcode" in changes:
        code = _barcode(changes["barcode"])
        if code and _barcode_used(session, code, product_id):
            raise ValueError("الباركود مستخدم لصنف آخر")
        row.barcode = code
        for old in list(row.barcodes):
            if old.is_primary:
                session.delete(old)
        if code:
            session.add(ProductBarcode(product_id=product_id, code=code,
                                       barcode_type="primary", is_primary=True))
    session.flush()
    return row

def archive_product(session: Session, product_id: int) -> Product:
    row = session.get(Product, product_id)
    if row is None:
        raise ValueError("الصنف غير موجود")
    row.is_active = False
    session.flush()
    return row
