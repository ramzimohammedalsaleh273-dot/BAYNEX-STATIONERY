from decimal import Decimal

import pytest

from baynex_stationery.domain.pricing import invoice_total, line_total, money


def test_line_total_uses_decimal_rounding():
    assert line_total("2.35", "3") == Decimal("7.05")


def test_invoice_total_applies_discount_then_tax():
    assert invoice_total("100", "10", "0.15") == Decimal("103.50")


def test_line_total_rejects_zero_quantity():
    with pytest.raises(ValueError):
        line_total("5", "0")


def test_invoice_total_rejects_discount_above_subtotal():
    with pytest.raises(ValueError):
        invoice_total("10", "11")


def test_money_rounds_half_up():
    assert money("1.005") == Decimal("1.01")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_money_rejects_non_finite_values(value):
    with pytest.raises(ValueError, match="محدوداً"):
        money(value)


def test_line_total_rejects_non_finite_quantity():
    with pytest.raises(ValueError, match="محدوداً"):
        line_total("5", "NaN")

