"""帳簿。請求書の置き場で、番号の採番と集計キャッシュも持つ。"""

from .audit import AuditLog
from .errors import NotFound, ValidationError

_ID_PREFIXES = {
    "invoice": "INV",
    "payment": "PAY",
}


class Book:
    """請求書・監査ログ・採番カウンタ・集計キャッシュをまとめて持つ。

    集計キャッシュは receivables と reports が読み書きする。集計の結果が変わる操作を
    したら、その操作の側で invalidate_* を呼ぶ。
    """

    def __init__(self):
        self.invoices = {}
        self.audit = AuditLog()
        self.counters = {"invoice": 0, "payment": 0}
        self.summary_cache = {}
        self.report_cache = {}

    def next_id(self, kind):
        """番号を採番する (INV-0001 のような帳簿全体の連番)"""
        if kind not in _ID_PREFIXES:
            raise ValidationError(f"未知の番号の種類: {kind}")
        self.counters[kind] += 1
        return f"{_ID_PREFIXES[kind]}-{self.counters[kind]:04d}"

    def add_invoice(self, invoice):
        self.invoices[invoice.invoice_id] = invoice

    def get_invoice(self, invoice_id):
        """請求書を返す。無ければ NotFound"""
        try:
            return self.invoices[invoice_id]
        except KeyError:
            raise NotFound(f"請求書がありません: {invoice_id}") from None

    def invoices_for(self, customer_id):
        """その顧客の請求書を番号順に返す"""
        found = [inv for inv in self.invoices.values() if inv.customer_id == customer_id]
        return sorted(found, key=lambda inv: inv.invoice_id)

    def all_invoices(self):
        """すべての請求書を番号順に返す"""
        return sorted(self.invoices.values(), key=lambda inv: inv.invoice_id)

    def invalidate_summary(self, customer_id):
        """その顧客の残高集計のキャッシュを捨てる"""
        self.summary_cache.pop(customer_id, None)

    def invalidate_report(self, year, month):
        """その月の月次集計のキャッシュを捨てる"""
        for key in [k for k in self.report_cache if k[1:] == (year, month)]:
            del self.report_cache[key]
