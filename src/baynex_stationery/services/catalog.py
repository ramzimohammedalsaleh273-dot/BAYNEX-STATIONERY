"""Category and unit-of-measure application services."""
from __future__ import annotations

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from baynex_stationery.db.models import Category, UnitOfMeasure


def _required(value: str, label: str, limit: int) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{label} مطلوب")
    if len(cleaned) > limit:
        raise ValueError(f"{label} يجب ألا يتجاوز {limit} حرفاً")
    return cleaned

def list_categories(session: Session, include_inactive: bool = False) -> list[Category]:
    stmt = select(Category).order_by(Category.name.asc())
    if not include_inactive:
        stmt = stmt.where(Category.is_active.is_(True))
    return list(session.scalars(stmt))

def create_category(session: Session, *, name: str, code: str | None = None,
                    parent_id: int | None = None, description: str | None = None) -> Category:
    name = _required(name, "اسم التصنيف", 120)
    code = code.strip() if code else ""
    if not code:
        code = "CAT-" + hashlib.sha1(name.casefold().encode("utf-8")).hexdigest()[:10].upper()
    code = _required(code, "رمز التصنيف", 32)
    if session.scalar(select(Category.id).where(func.lower(Category.name) == name.casefold())):
        raise ValueError("اسم التصنيف مستخدم بالفعل")
    if session.scalar(select(Category.id).where(func.lower(Category.code) == code.casefold())):
        raise ValueError("رمز التصنيف مستخدم بالفعل")
    if parent_id is not None:
        parent = session.get(Category, parent_id)
        if parent is None or not parent.is_active:
            raise ValueError("التصنيف الأب غير موجود أو غير نشط")
    row = Category(name=name, code=code, parent_id=parent_id,
                   description=description.strip() if description else None)
    session.add(row)
    session.flush()
    return row

def set_category_active(session: Session, category_id: int, active: bool) -> Category:
    row = session.get(Category, category_id)
    if row is None:
        raise ValueError("التصنيف غير موجود")
    row.is_active = bool(active)
    session.flush()
    return row

def list_units(session: Session, include_inactive: bool = False) -> list[UnitOfMeasure]:
    stmt = select(UnitOfMeasure).order_by(UnitOfMeasure.name.asc())
    if not include_inactive:
        stmt = stmt.where(UnitOfMeasure.is_active.is_(True))
    return list(session.scalars(stmt))

def create_unit(session: Session, *, code: str, name: str, symbol: str,
                decimal_places: int = 3) -> UnitOfMeasure:
    code = _required(code, "رمز الوحدة", 20)
    name = _required(name, "اسم الوحدة", 60)
    symbol = _required(symbol, "اختصار الوحدة", 20)
    if not 0 <= decimal_places <= 3:
        raise ValueError("عدد الخانات العشرية للوحدة يجب أن يكون بين صفر وثلاث")
    if session.scalar(select(UnitOfMeasure.id).where(func.lower(UnitOfMeasure.code) == code.casefold())):
        raise ValueError("رمز الوحدة مستخدم بالفعل")
    if session.scalar(select(UnitOfMeasure.id).where(func.lower(UnitOfMeasure.name) == name.casefold())):
        raise ValueError("اسم الوحدة مستخدم بالفعل")
    row = UnitOfMeasure(code=code, name=name, symbol=symbol, decimal_places=decimal_places)
    session.add(row)
    session.flush()
    return row

def set_unit_active(session: Session, unit_id: int, active: bool) -> UnitOfMeasure:
    row = session.get(UnitOfMeasure, unit_id)
    if row is None:
        raise ValueError("الوحدة غير موجودة")
    row.is_active = bool(active)
    session.flush()
    return row
