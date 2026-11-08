"""値引きの按分と税額の計算。

請求書の金額の決まり方:
1. 値引き (allowance) を明細の小計の比で按分し、明細ごとの純額を決める
2. 税額は明細ごとではなく税率ごとに計算する。同じ税率の明細の純額を合計し、
   税率を掛けて、通貨の最小単位に切り捨てる
3. 請求額は純額の合計と税額の合計の和
"""

from collections import OrderedDict, namedtuple

from .money import allocate, truncate_money, zero

Totals = namedtuple("Totals", ["subtotal", "allowance", "net", "tax", "total"])


def line_nets(invoice):
    """明細ごとの純額 (値引き按分後の税抜金額) を {line_id: 金額} で返す"""
    subtotals = [line.subtotal() for line in invoice.lines]
    shares = allocate(invoice.allowance, subtotals, invoice.currency)
    return OrderedDict(
        (line.line_id, subtotal - share)
        for line, subtotal, share in zip(invoice.lines, subtotals, shares)
    )


def tax_on(base, rate, currency):
    """同じ税率の純額の合計 base に対する税額を返す"""
    return truncate_money(base * rate, currency)


def nets_by_rate(invoice):
    """税率ごとの純額の合計を {税率: 金額} で返す"""
    nets = line_nets(invoice)
    grouped = OrderedDict()
    for line in invoice.lines:
        grouped[line.tax_rate] = grouped.get(line.tax_rate, zero(invoice.currency)) + nets[line.line_id]
    return grouped


def taxes_by_rate(invoice):
    """税率ごとの税額を {税率: 金額} で返す"""
    return OrderedDict(
        (rate, tax_on(base, rate, invoice.currency))
        for rate, base in nets_by_rate(invoice).items()
    )


def totals(invoice):
    """請求書の金額をまとめて返す"""
    subtotal = sum((line.subtotal() for line in invoice.lines), zero(invoice.currency))
    net = sum(line_nets(invoice).values(), zero(invoice.currency))
    tax = sum(taxes_by_rate(invoice).values(), zero(invoice.currency))
    return Totals(subtotal, invoice.allowance, net, tax, net + tax)


def paid_total(invoice):
    """入金の合計を返す"""
    return sum((p.amount for p in invoice.payments), zero(invoice.currency))


def balance_due(invoice):
    """請求額のうち未入金の額を返す"""
    return totals(invoice).total - paid_total(invoice)
