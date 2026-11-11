from decimal import Decimal

import pytest

from baynex_stationery.services.pos import calculate_line, calculate_totals


def test_pos_calculates_fractional_quantity_and_discount():
    line = calculate_line("2.500", "12.00", "2.00")
    assert line["gross"] == Decimal("30.00")
    assert line["total"] == Decimal("28.00")
    totals = calculate_totals([line], "3.00")
    assert totals == {
        "subtotal": Decimal("30.00"),
        "discount": Decimal("5.00"),
        "total": Decimal("25.00"),
    }


@pytest.mark.parametrize("quantity", ["0", "-1", "1.0001", "nan", "bad"])
def test_pos_rejects_invalid_quantity(quantity):
    with pytest.raises(ValueError):
        calculate_line(quantity, "1.00")


def test_pos_rejects_discount_above_line_total():
    with pytest.raises(ValueError, match="الخصم"):
        calculate_line("1", "5.00", "6.00")


def test_pos_rejects_invoice_discount_above_net():
    line = calculate_line("1", "5.00")
    with pytest.raises(ValueError, match="خصم الفاتورة"):
        calculate_totals([line], "5.01")
