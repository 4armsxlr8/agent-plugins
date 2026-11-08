"""入金の記録。"""

from decimal import Decimal

from .errors import InvalidTransition, ValidationError
from .models import ISSUED, PAID, PARTIALLY_PAID, Payment
from .money import format_amount, is_payable_amount
from .pricing import balance_due
from .transitions import transition

METHODS = ("bank_transfer", "card", "cash")


def record_payment(book, invoice_id, amount, method, actor, on):
    """入金を記録する。未入金の額を超える入金は受け付けない。

    payment.recorded を記録し、状態が変わるときはそのあとに
    invoice.status_changed が続く。入金で顧客の残高が変わる。売上は発行時に
    計上済みなので月次集計は変わらない。
    """
    invoice = book.get_invoice(invoice_id)
    if invoice.status not in (ISSUED, PARTIALLY_PAID):
        raise InvalidTransition(f"{invoice_id}: {invoice.status} の請求書には入金できません")
    amount = Decimal(amount)
    if not is_payable_amount(amount, invoice.currency):
        raise ValidationError(f"入金額が不正です: {amount}")
    if method not in METHODS:
        raise ValidationError(f"未知の入金方法: {method}")
    due = balance_due(invoice)
    if amount > due:
        raise ValidationError(f"未入金の額を超えています: {amount} > {due}")

    payment = Payment(book.next_id("payment"), amount, on, method)
    invoice.payments.append(payment)
    book.audit.append(
        "payment.recorded",
        invoice.invoice_id,
        actor,
        on,
        {"payment_id": payment.payment_id, "amount": format_amount(amount, invoice.currency), "method": method},
    )
    next_status = PAID if amount == due else PARTIALLY_PAID
    if next_status != invoice.status:
        transition(book, invoice, next_status, actor, on)
    book.invalidate_summary(invoice.customer_id)
    return payment
