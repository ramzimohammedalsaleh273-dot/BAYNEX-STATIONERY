"""Deterministic money calculations using finite Decimal values."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")


def decimal_value(value: Decimal | str | int, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} يجب أن يكون رقماً صالحاً") from exc
    if not result.is_finite():
        raise ValueError(f"{field_name} يجب أن يكون رقماً محدوداً")
    return result


def money(value: Decimal | str | int) -> Decimal:
    amount = decimal_value(value, "المبلغ")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def line_total(unit_price: Decimal | str, quantity: Decimal | str) -> Decimal:
    price = decimal_value(unit_price, "سعر البيع")
    qty = decimal_value(quantity, "الكمية")
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
    rate = decimal_value(tax_rate, "نسبة الضريبة")
    if base < 0 or discount_value < 0 or discount_value > base:
        raise ValueError("قيمة الخصم غير صحيحة")
    if rate < 0 or rate > 1:
        raise ValueError("نسبة الضريبة يجب أن تكون بين صفر وواحد")
    taxable = base - discount_value
    return money(taxable + taxable * rate)
