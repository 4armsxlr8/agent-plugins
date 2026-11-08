"""月次の売上と税額の集計。

請求書は発行日の月に計上する。結果は (集計の名前, 年, 月) をキーに帳簿にキャッシュする。
"""

import copy

from .models import ISSUED, PAID, PARTIALLY_PAID
from .money import zero
from .pricing import nets_by_rate, taxes_by_rate, totals

_RECOGNIZED_STATUSES = (ISSUED, PARTIALLY_PAID, PAID)


def _cached(book, name, year, month, compute):
    key = (name, year, month)
    if key not in book.report_cache:
        book.report_cache[key] = compute(book, year, month)
    return copy.deepcopy(book.report_cache[key])


def _recognized_in(book, year, month):
    for invoice in book.all_invoices():
        if invoice.status not in _RECOGNIZED_STATUSES:
            continue
        if (invoice.issued_on.year, invoice.issued_on.month) == (year, month):
            yield invoice


def monthly_revenue(book, year, month):
    """その月の売上 (純額の合計) を {通貨: 金額} で返す"""
    return _cached(book, "revenue", year, month, _compute_revenue)


def _compute_revenue(book, year, month):
    revenue = {}
    for invoice in _recognized_in(book, year, month):
        currency = invoice.currency
        revenue[currency] = revenue.get(currency, zero(currency)) + totals(invoice).net
    return revenue


def tax_report(book, year, month):
    """その月の税額を {通貨: {税率: 金額}} で返す"""
    return _cached(book, "tax", year, month, _compute_tax)


def _compute_tax(book, year, month):
    report = {}
    for invoice in _recognized_in(book, year, month):
        by_rate = report.setdefault(invoice.currency, {})
        for rate, tax in taxes_by_rate(invoice).items():
            by_rate[rate] = by_rate.get(rate, zero(invoice.currency)) + tax
    return report


def taxable_base_report(book, year, month):
    """その月の課税対象の純額を {通貨: {税率: 金額}} で返す。発行分のみ"""
    report = {}
    for invoice in _recognized_in(book, year, month):
        by_rate = report.setdefault(invoice.currency, {})
        for rate, base in nets_by_rate(invoice).items():
            by_rate[rate] = by_rate.get(rate, zero(invoice.currency)) + base
    return report
