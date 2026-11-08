"""請求書の作成・編集・発行・取り消し・複製。"""

from dataclasses import replace
from decimal import Decimal

from .errors import InvalidTransition, ValidationError
from .models import DRAFT, ISSUED, PARTIALLY_PAID, VOID, Invoice, Line
from .money import is_payable_amount, zero
from .pricing import totals
from .transitions import transition


def normalize_quantities(quantities):
    """line_id → 数量 の対応を整えて返す。

    数量は整数にそろえ、0 の行は除く。整数で表せない数量は ValidationError。
    """
    for line_id in list(quantities):
        value = quantities[line_id]
        if int(value) != value:
            raise ValidationError(f"数量は整数で指定してください: {line_id} {value}")
        if value == 0:
            del quantities[line_id]
        else:
            quantities[line_id] = int(value)
    return quantities


def _draft(book, invoice_id):
    invoice = book.get_invoice(invoice_id)
    if invoice.status != DRAFT:
        raise InvalidTransition(f"{invoice_id}: 下書き以外は編集できません")
    return invoice


def create_invoice(book, customer_id, currency, memo=""):
    """空の下書きを作って返す"""
    invoice = Invoice(
        invoice_id=book.next_id("invoice"),
        customer_id=customer_id,
        currency=currency,
        allowance=zero(currency),
        memo=memo,
    )
    book.add_invoice(invoice)
    return invoice


def add_line(book, invoice_id, sku, description, unit_price, quantity, tax_rate):
    """下書きに明細を足して返す"""
    invoice = _draft(book, invoice_id)
    unit_price, tax_rate = Decimal(unit_price), Decimal(tax_rate)
    if quantity <= 0 or int(quantity) != quantity:
        raise ValidationError(f"数量は正の整数で指定してください: {quantity}")
    if unit_price < 0:
        raise ValidationError(f"単価は負にできません: {unit_price}")
    line = Line(invoice.next_line_id(), sku, description, unit_price, int(quantity), tax_rate)
    invoice.lines.append(line)
    return line


def remove_line(book, invoice_id, line_id):
    """下書きから明細を取り除く"""
    invoice = _draft(book, invoice_id)
    invoice.lines.remove(invoice.line(line_id))


def amend_quantities(book, invoice_id, deltas):
    """下書きの明細の数量を増減する。deltas は line_id → 増減量。

    増減後の数量が 0 以下になる行があれば、どの行も変えずに ValidationError。
    """
    invoice = _draft(book, invoice_id)
    changes = normalize_quantities(dict(deltas))
    for line_id, delta in changes.items():
        if invoice.line(line_id).quantity + delta <= 0:
            raise ValidationError(f"数量が 0 以下になります: {line_id}")
    for line_id, delta in changes.items():
        invoice.line(line_id).quantity += delta


def set_allowance(book, invoice_id, amount):
    """下書きの値引き額を設定する"""
    invoice = _draft(book, invoice_id)
    amount = Decimal(amount)
    if amount < 0:
        raise ValidationError(f"値引き額は負にできません: {amount}")
    if amount != 0 and not is_payable_amount(amount, invoice.currency):
        raise ValidationError(f"通貨の最小単位で表せません: {amount}")
    if amount > sum(line.subtotal() for line in invoice.lines):
        raise ValidationError("値引き額が小計を超えています")
    invoice.allowance = amount


def issue_invoice(book, invoice_id, actor, on, due_on):
    """下書きを発行する。発行日の月の売上と顧客の残高が変わる"""
    invoice = _draft(book, invoice_id)
    if not invoice.lines:
        raise ValidationError(f"{invoice_id}: 明細のない請求書は発行できません")
    if totals(invoice).total <= 0:
        raise ValidationError(f"{invoice_id}: 請求額が 0 の請求書は発行できません")
    transition(book, invoice, ISSUED, actor, on)
    invoice.issued_on = on
    invoice.due_on = due_on
    book.invalidate_summary(invoice.customer_id)
    book.invalidate_report(on.year, on.month)
    return invoice


def void_invoice(book, invoice_id, actor, on):
    """下書きか未入金の請求書を取り消す。発行済みだった月の売上と顧客の残高が変わる"""
    invoice = book.get_invoice(invoice_id)
    if invoice.status == PARTIALLY_PAID or invoice.payments:
        raise InvalidTransition(f"{invoice_id}: 入金のある請求書は取り消せません")
    issued_on = invoice.issued_on
    transition(book, invoice, VOID, actor, on)
    book.invalidate_summary(invoice.customer_id)
    if issued_on is not None:
        book.invalidate_report(issued_on.year, issued_on.month)
    return invoice


def duplicate_invoice(book, invoice_id, memo=""):
    """請求書の内容を写した新しい下書きを作って返す。入金は引き継がない"""
    source = book.get_invoice(invoice_id)
    copy = replace(
        source,
        invoice_id=book.next_id("invoice"),
        lines=[replace(line) for line in source.lines],
        status=DRAFT,
        issued_on=None,
        due_on=None,
        payments=[],
        memo=memo,
    )
    book.add_invoice(copy)
    return copy
