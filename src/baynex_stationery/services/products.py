"""Product application service."""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from baynex_stationery.db.models import Product


def list_products(session: Session, include_inactive: bool = False) -> list[Product]:
    statement = select(Product).order_by(Product.name.asc())
    if not include_inactive:
        statement = statement.where(Product.is_active.is_(True))
    return list(session.scalars(statement))


def create_product(
    session: Session, *, sku: str, name: str, sale_price: Decimal,
    cost_price: Decimal = Decimal("0"), opening_stock: Decimal = Decimal("0"),
    barcode: str | None = None, unit: str = "قطعة",
) -> Product:
    sku, name = sku.strip(), name.strip()
    if not sku or not name:
        raise ValueError("رمز الصنف واسم الصنف مطلوبان")
    if sale_price < 0 or cost_price < 0 or opening_stock < 0:
        raise ValueError("الأسعار والرصيد الافتتاحي لا يمكن أن تكون سالبة")
    product = Product(
        sku=sku, name=name, sale_price=sale_price, cost_price=cost_price,
        stock_quantity=opening_stock, barcode=barcode.strip() or None if barcode else None,
        unit=unit.strip() or "قطعة",
    )
    session.add(product)
    session.flush()
    return product
