"""Deterministic money calculations using Decimal."""
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(value: Decimal | str | int) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def line_total(unit_price: Decimal | str, quantity: Decimal | str) -> Decimal:
    price = Decimal(str(unit_price))
    qty = Decimal(str(quantity))
    if price < 0:
        raise ValueError("سعر البيع لا يمكن أن يكون سالباً")
    if qty <= 0:
        raise ValueError("الكمية يجب أن تكون أكبر من صفر")
    return money(price * qty)


def invoice_total(
    subtotal: Decimal | str,
    discount: Decimal | str = "0",
    tax_rate: Decimal | str = "0",
) -> Decimal:
    base = money(subtotal)
    discount_value = money(discount)
    rate = Decimal(str(tax_rate))
    if base < 0 or discount_value < 0 or discount_value > base:
        raise ValueError("قيمة الخصم غير صحيحة")
    if rate < 0 or rate > 1:
        raise ValueError("نسبة الضريبة يجب أن تكون بين صفر وواحد")
    taxable = base - discount_value
    return money(taxable + taxable * rate)
