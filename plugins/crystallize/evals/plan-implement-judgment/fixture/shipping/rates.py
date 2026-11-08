import csv
from decimal import Decimal

WEIGHT_BANDS = ((500, 410), (2000, 615), (5000, 850), (10000, 1200), (20000, 1815))
REMOTE_ZONES = frozenset({"hokkaido", "okinawwa"})
REMOTE_SURCHARGE = 400
FREE_SHIPPING_THRESHOLD = 10000
TAX_RATE = Decimal("0.10")


def band_fee(weight_g):
    for limit, fee in WEIGHT_BANDS:
        if weight_g <= limit:
            return fee
    raise ValueError(f"重量の上限を超えています: {weight_g}")


def load_legacy_rates(path):
    """経理が配布する旧料金表を {zone: 料金} で読む"""
    with open(path, newline="", encoding="utf-8") as f:
        return {row["zone"]: int(row["fee"]) for row in csv.DictReader(f)}
