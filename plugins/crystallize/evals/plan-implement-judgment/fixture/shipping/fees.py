from decimal import Decimal

from .money import round_yen
from .rates import FREE_SHIPPING_THRESHOLD, REMOTE_SURCHARGE, REMOTE_ZONES, TAX_RATE, band_fee


def quote(parcel):
    base = 0 if parcel.subtotal > FREE_SHIPPING_THRESHOLD else band_fee(parcel.weight_g)
    remote = REMOTE_SURCHARGE if parcel.zone in REMOTE_ZONES else 0
    tax = round_yen(Decimal(base + remote) * TAX_RATE)
    return {"breakdown": {"base": base, "remote": remote, "tax": tax}, "total": base + remote + tax}
