"""請求書とその明細・入金のデータ。"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional

from .errors import NotFound

DRAFT = "draft"
ISSUED = "issued"
PARTIALLY_PAID = "partially_paid"
PAID = "paid"
VOID = "void"


@dataclass
class Line:
    """請求書の明細 1 行。"""

    line_id: str
    sku: str
    description: str
    unit_price: Decimal
    quantity: int
    tax_rate: Decimal

    def subtotal(self):
        """値引き前の税抜金額"""
        return self.unit_price * self.quantity


@dataclass
class Payment:
    """入金 1 件。"""

    payment_id: str
    amount: Decimal
    paid_on: date
    method: str


@dataclass
class Invoice:
    """請求書。

    lines は発行後は変更しない。allowance は請求書全体にかける値引き額 (税抜)。
    """

    invoice_id: str
    customer_id: str
    currency: str
    lines: List[Line] = field(default_factory=list)
    allowance: Decimal = Decimal(0)
    status: str = DRAFT
    issued_on: Optional[date] = None
    due_on: Optional[date] = None
    payments: List[Payment] = field(default_factory=list)
    memo: str = ""

    def line(self, line_id):
        """明細を返す。無ければ NotFound"""
        for line in self.lines:
            if line.line_id == line_id:
                return line
        raise NotFound(f"明細がありません: {self.invoice_id} {line_id}")

    def next_line_id(self):
        """この請求書で未使用の明細番号を返す (L1, L2, ...)"""
        numbers = [int(line.line_id[1:]) for line in self.lines]
        return f"L{max(numbers, default=0) + 1}"
