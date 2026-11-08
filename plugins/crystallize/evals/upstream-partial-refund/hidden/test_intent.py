"""依頼文に無く、モデルの既定の判断とも違う意図を実装できたかを判断ごとに確かめる。クラスが判断 1 つに対応する"""

import unittest
from datetime import date
from decimal import Decimal as D

from billing.book import Book
from billing.errors import BillingError
from billing.invoices import add_line, create_invoice, issue_invoice
from billing.payments import record_payment
from billing.pricing import totals
from billing.receivables import customer_statement
from billing.refunds import issue_refund, refunds_for
from billing.store import dump_book

ISSUED_ON = date(2026, 3, 10)
ON = date(2026, 4, 15)


def paid_invoice(book):
    invoice = create_invoice(book, "C1", "JPY")
    add_line(book, invoice.invoice_id, "SKU", "商品", "1000", 3, "0.10")
    issue_invoice(book, invoice.invoice_id, "alice", ISSUED_ON, date(2026, 3, 31))
    record_payment(book, invoice.invoice_id, totals(invoice).total, "cash", "alice", date(2026, 3, 20))
    return invoice


class Deadline(unittest.TestCase):
    def test_after_180_days_is_rejected(self):
        book = Book()
        invoice = paid_invoice(book)
        # 例外の型は問わない。依頼者役が型まで答えるとは限らない
        with self.assertRaises(BillingError):
            issue_refund(book, invoice.invoice_id, {"L1": 1}, "返品", "alice", date(2026, 9, 7))  # 181 日目
        self.assertEqual(list(refunds_for(book, invoice.invoice_id)), [])

    def test_day_180_is_allowed(self):
        book = Book()
        invoice = paid_invoice(book)
        self.assertEqual(issue_refund(book, invoice.invoice_id, {"L1": 1}, "返品", "alice", date(2026, 9, 6)).issued_on, date(2026, 9, 6))


class BlankReason(unittest.TestCase):
    def test_blank_reason_is_recorded(self):
        book = Book()
        invoice = paid_invoice(book)
        self.assertEqual(issue_refund(book, invoice.invoice_id, {"L1": 1}, "", "alice", ON).reason, "")


class BeforeIssue(unittest.TestCase):
    def test_refund_before_issue_date_is_recorded(self):
        book = Book()
        invoice = paid_invoice(book)
        self.assertEqual(issue_refund(book, invoice.invoice_id, {"L1": 1}, "返品", "alice", date(2026, 3, 9)).issued_on, date(2026, 3, 9))


class StatementRefunded(unittest.TestCase):
    def test_statement_row_has_refunded(self):
        book = Book()
        invoice = paid_invoice(book)
        self.assertEqual(customer_statement(book, "C1")[0]["refunded"], D("0"))
        issue_refund(book, invoice.invoice_id, {"L1": 1}, "返品", "alice", ON)
        row = customer_statement(book, "C1")[0]
        self.assertEqual((row["refunded"], row["total"], row["paid"]), (D("1100"), D("3300"), D("3300")))


class SchemaVersion(unittest.TestCase):
    def test_saved_format_stays_at_version_1(self):
        book = Book()
        invoice = paid_invoice(book)
        issue_refund(book, invoice.invoice_id, {"L1": 1}, "返品", "alice", ON)
        self.assertEqual(dump_book(book)["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
