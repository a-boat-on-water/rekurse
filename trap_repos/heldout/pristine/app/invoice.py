"""Invoice totals."""
from decimal import ROUND_HALF_UP, Decimal

from app.rates import get_rate


def round_money(x: float) -> float:
    """Round half up to cents (banker's rounding would be wrong for invoices)."""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def total(items: list[tuple[float, int]], currency: str) -> float:
    """Sum of price*qty in USD, converted to `currency` and rounded to cents."""
    raw = sum(price * qty for price, qty in items)
    return round_money(raw * get_rate(currency))
