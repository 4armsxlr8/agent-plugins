from dataclasses import dataclass


@dataclass(frozen=True)
class Parcel:
    weight_g: int
    zone: str
    subtotal: int  # 商品代金
    temperature: str = "normal"  # normal / chilled / frozen
