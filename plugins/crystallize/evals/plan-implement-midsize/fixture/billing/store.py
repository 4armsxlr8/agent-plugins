"""帳簿の保存と読み込み。

保存形式は JSON。金額と税率は文字列、日付は ISO 形式の文字列で書く。
集計キャッシュは保存しない。読み込み直後に計算し直される。
"""

import json
import os
from datetime import date
from decimal import Decimal

from .audit import AuditLog
from .book import Book
from .errors import StoreError
from .models import Invoice, Line, Payment

SCHEMA_VERSION = 1


def _date_to_text(value):
    return value.isoformat() if value is not None else None


def _date_from_text(text):
    return date.fromisoformat(text) if text is not None else None


def _line_to_dict(line):
    return {
        "line_id": line.line_id,
        "sku": line.sku,
        "description": line.description,
        "unit_price": str(line.unit_price),
        "quantity": line.quantity,
        "tax_rate": str(line.tax_rate),
    }


def _line_from_dict(data):
    return Line(
        line_id=data["line_id"],
        sku=data["sku"],
        description=data["description"],
        unit_price=Decimal(data["unit_price"]),
        quantity=data["quantity"],
        tax_rate=Decimal(data["tax_rate"]),
    )


def _payment_to_dict(payment):
    return {
        "payment_id": payment.payment_id,
        "amount": str(payment.amount),
        "paid_on": payment.paid_on.isoformat(),
        "method": payment.method,
    }


def _payment_from_dict(data):
    return Payment(
        payment_id=data["payment_id"],
        amount=Decimal(data["amount"]),
        paid_on=date.fromisoformat(data["paid_on"]),
        method=data["method"],
    )


def _invoice_to_dict(invoice):
    return {
        "invoice_id": invoice.invoice_id,
        "customer_id": invoice.customer_id,
        "currency": invoice.currency,
        "lines": [_line_to_dict(line) for line in invoice.lines],
        "allowance": str(invoice.allowance),
        "status": invoice.status,
        "issued_on": _date_to_text(invoice.issued_on),
        "due_on": _date_to_text(invoice.due_on),
        "payments": [_payment_to_dict(p) for p in invoice.payments],
        "memo": invoice.memo,
    }


def _invoice_from_dict(data):
    return Invoice(
        invoice_id=data["invoice_id"],
        customer_id=data["customer_id"],
        currency=data["currency"],
        lines=[_line_from_dict(item) for item in data["lines"]],
        allowance=Decimal(data["allowance"]),
        status=data["status"],
        issued_on=_date_from_text(data["issued_on"]),
        due_on=_date_from_text(data["due_on"]),
        payments=[_payment_from_dict(item) for item in data["payments"]],
        memo=data["memo"],
    )


def dump_book(book):
    """帳簿を JSON にできる dict にする"""
    return {
        "schema_version": SCHEMA_VERSION,
        "counters": {
            "invoice": book.counters["invoice"],
            "payment": book.counters["payment"],
        },
        "invoices": [_invoice_to_dict(inv) for inv in book.all_invoices()],
        "audit": book.audit.to_list(),
    }


def load_book(data):
    """dump_book の結果から帳簿を作る"""
    if data.get("schema_version") != SCHEMA_VERSION:
        raise StoreError(f"未対応の保存形式: {data.get('schema_version')}")
    book = Book()
    book.counters["invoice"] = data["counters"]["invoice"]
    book.counters["payment"] = data["counters"]["payment"]
    for item in data["invoices"]:
        book.add_invoice(_invoice_from_dict(item))
    book.audit = AuditLog.from_list(data["audit"])
    return book


def save(book, path):
    """帳簿をファイルに保存する。書き込みの途中で失敗しても元のファイルを壊さない"""
    text = json.dumps(dump_book(book), ensure_ascii=False, indent=2, sort_keys=True)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(temp_path, path)


def load(path):
    """ファイルから帳簿を読み込む"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        raise StoreError(f"読み込めません: {path}: {exc}") from exc
    return load_book(data)
