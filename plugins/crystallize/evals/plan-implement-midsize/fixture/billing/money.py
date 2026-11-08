"""金額の丸め・按分・文字列表現。

金額はすべて Decimal で扱う。通貨ごとの最小単位は CURRENCY_DIGITS で決まる。
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from .errors import ValidationError

CURRENCY_DIGITS = {
    "JPY": 0,
    "USD": 2,
    "EUR": 2,
}


def _unit(currency):
    """通貨の最小単位を Decimal で返す (JPY は 1、USD は 0.01)"""
    try:
        digits = CURRENCY_DIGITS[currency]
    except KeyError:
        raise ValidationError(f"未対応の通貨: {currency}") from None
    return Decimal(1).scaleb(-digits)


def zero(currency):
    """その通貨の 0 を返す"""
    return Decimal(0).quantize(_unit(currency))


def round_money(amount, currency):
    """金額を通貨の最小単位に四捨五入する。税額以外の金額の丸めはこれを使う"""
    return Decimal(amount).quantize(_unit(currency), rounding=ROUND_HALF_UP)


def truncate_money(amount, currency):
    """金額を通貨の最小単位に切り捨てる。税額の端数処理はこれを使う"""
    return Decimal(amount).quantize(_unit(currency), rounding=ROUND_DOWN)


def format_amount(amount, currency):
    """金額を通貨の桁に揃えた文字列にする (JPY は "1072"、USD は "11.01")"""
    return str(round_money(amount, currency))


def parse_amount(text):
    """保存された文字列を金額に戻す"""
    return Decimal(text)


def is_payable_amount(amount, currency):
    """その通貨の最小単位で表せる正の金額か"""
    return amount > 0 and round_money(amount, currency) == amount


def allocate(total, weights, currency):
    """total を weights の比で按分する。

    各要素を最小単位に切り捨て、余りを小数部の大きい要素から順に 1 単位ずつ配る
    (同じなら先の要素から)。戻り値の合計は必ず total に一致する。
    """
    weight_sum = sum(weights)
    if weight_sum == 0:
        return [zero(currency) for _ in weights]
    exact = [Decimal(total) * Decimal(w) / Decimal(weight_sum) for w in weights]
    parts = [truncate_money(x, currency) for x in exact]
    remainder = Decimal(total) - sum(parts)
    unit = _unit(currency)
    by_fraction = sorted(range(len(parts)), key=lambda i: (parts[i] - exact[i], i))
    for i in by_fraction:
        if remainder < unit:
            break
        parts[i] += unit
        remainder -= unit
    return parts
