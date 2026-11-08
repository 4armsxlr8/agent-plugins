from decimal import ROUND_DOWN, Decimal


def round_yen(amount):
    """円未満を切り捨てる (約款 8 条)"""
    return int(Decimal(amount).quantize(Decimal("1"), rounding=ROUND_DOWN))
