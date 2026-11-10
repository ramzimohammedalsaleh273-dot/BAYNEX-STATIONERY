"""Category and unit catalog services."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from baynex_stationery.db.models import Category, Unit


def create_category(session: Session, name: str, description: str | None = None) -> Category:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("اسم التصنيف مطلوب")
    if len(clean_name) > 120:
        raise ValueError("اسم التصنيف لا يتجاوز 120 حرفاً")
    category = Category(name=clean_name, description=description.strip() or None if description else None)
    session.add(category)
    session.flush()
    return category


def list_categories(session: Session, include_inactive: bool = False) -> list[Category]:
    statement = select(Category).order_by(Category.name.asc())
    if not include_inactive:
        statement = statement.where(Category.is_active.is_(True))
    return list(session.scalars(statement))


def set_category_active(session: Session, category_id: int, active: bool) -> Category:
    category = session.get(Category, category_id)
    if category is None:
        raise ValueError("التصنيف غير موجود")
    category.is_active = bool(active)
    session.flush()
    return category


def create_unit(session: Session, name: str, symbol: str) -> Unit:
    clean_name, clean_symbol = name.strip(), symbol.strip()
    if not clean_name or not clean_symbol:
        raise ValueError("اسم الوحدة ورمزها مطلوبان")
    if len(clean_name) > 80 or len(clean_symbol) > 24:
        raise ValueError("اسم الوحدة أو رمزها أطول من الحد المسموح")
    unit = Unit(name=clean_name, symbol=clean_symbol)
    session.add(unit)
    session.flush()
    return unit


def list_units(session: Session, include_inactive: bool = False) -> list[Unit]:
    statement = select(Unit).order_by(Unit.name.asc())
    if not include_inactive:
        statement = statement.where(Unit.is_active.is_(True))
    return list(session.scalars(statement))


def set_unit_active(session: Session, unit_id: int, active: bool) -> Unit:
    unit = session.get(Unit, unit_id)
    if unit is None:
        raise ValueError("الوحدة غير موجودة")
    unit.is_active = bool(active)
    session.flush()
    return unit
