"""Point-of-sale calculations shared by the cashier UI and tests."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
QTY = Decimal("0.001")


def decimal_input(value: object, label: str, *, minimum: Decimal = Decimal(0)) -> Decimal:
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} غير صالح") from exc
    if not result.is_finite() or result < minimum:
        raise ValueError(f"{label} يجب أن يكون رقماً محدوداً وغير سالب")
    return result


def calculate_line(quantity: object, unit_price: object, discount: object = 0) -> dict[str, Decimal]:
    qty = decimal_input(quantity, "الكمية", minimum=QTY)
    price = decimal_input(unit_price, "سعر الوحدة")
    off = decimal_input(discount, "الخصم")
    if qty != qty.quantize(QTY):
        raise ValueError("الكمية تقبل حتى ثلاث خانات عشرية")
    if price != price.quantize(CENT) or off != off.quantize(CENT):
        raise ValueError("السعر والخصم يقبلان خانتين عشريتين")
    gross = (qty * price).quantize(CENT, rounding=ROUND_HALF_UP)
    if off > gross:
        raise ValueError("الخصم أكبر من إجمالي السطر")
    return {"quantity": qty, "unit_price": price, "discount": off, "gross": gross, "total": gross - off}


def calculate_totals(lines: list[dict], invoice_discount: object = 0) -> dict[str, Decimal]:
    subtotal = sum((line["gross"] for line in lines), Decimal("0.00"))
    line_discounts = sum((line["discount"] for line in lines), Decimal("0.00"))
    off = decimal_input(invoice_discount, "خصم الفاتورة")
    if off != off.quantize(CENT):
        raise ValueError("خصم الفاتورة يقبل خانتين عشريتين")
    if off > subtotal - line_discounts:
        raise ValueError("خصم الفاتورة أكبر من صافي الأصناف")
    discounts = line_discounts + off
    return {"subtotal": subtotal, "discount": discounts, "total": subtotal - discounts}
