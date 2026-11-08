"""顧客ごとの残高と督促対象。"""

import copy

from .models import DRAFT, ISSUED, PAID, PARTIALLY_PAID, VOID
from .money import zero
from .pricing import balance_due, paid_total, totals

_BILLED_STATUSES = (ISSUED, PARTIALLY_PAID, PAID)
_NOT_COLLECTED = (DRAFT, VOID, PAID)


def customer_summary(book, customer_id):
    """顧客の残高を通貨ごとに返す。

    {通貨: {"billed": 請求額の合計, "paid": 入金の合計, "outstanding": 未入金の額, "invoice_count": 件数}}
    下書きと取り消し済みは数えない。結果は帳簿にキャッシュする。
    """
    cached = book.summary_cache.get(customer_id)
    if cached is None:
        cached = _compute_summary(book, customer_id)
        book.summary_cache[customer_id] = cached
    return copy.deepcopy(cached)


def _compute_summary(book, customer_id):
    summary = {}
    for invoice in book.invoices_for(customer_id):
        if invoice.status not in _BILLED_STATUSES:
            continue
        currency = invoice.currency
        row = summary.setdefault(
            currency,
            {"billed": zero(currency), "paid": zero(currency), "outstanding": zero(currency), "invoice_count": 0},
        )
        row["billed"] += totals(invoice).total
        row["paid"] += paid_total(invoice)
        row["outstanding"] += balance_due(invoice)
        row["invoice_count"] += 1
    return summary


def overdue_invoices(book, as_of):
    """支払期日を過ぎても入金の済んでいない請求書を、期日の古い順に返す。督促の対象"""
    overdue = []
    for invoice in book.all_invoices():
        if invoice.status in _NOT_COLLECTED:
            continue
        if invoice.due_on < as_of:
            overdue.append(invoice)
    return sorted(overdue, key=lambda inv: (inv.due_on, inv.invoice_id))


def overdue_amount(book, customer_id, as_of):
    """顧客の督促対象の未入金額を通貨ごとに返す"""
    amounts = {}
    for invoice in overdue_invoices(book, as_of):
        if invoice.customer_id != customer_id:
            continue
        amounts[invoice.currency] = amounts.get(invoice.currency, zero(invoice.currency)) + balance_due(invoice)
    return amounts


def customer_statement(book, customer_id):
    """顧客に送る明細書の行を返す。下書きは載せない"""
    rows = []
    for invoice in book.invoices_for(customer_id):
        if invoice.status == DRAFT:
            continue
        rows.append(
            {
                "invoice_id": invoice.invoice_id,
                "status": invoice.status,
                "issued_on": invoice.issued_on,
                "total": totals(invoice).total,
                "paid": paid_total(invoice),
            }
        )
    return rows
