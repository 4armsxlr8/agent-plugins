import unittest
from datetime import date
from decimal import Decimal as D

from billing.book import Book
from billing.invoices import add_line, create_invoice, issue_invoice, void_invoice
from billing.payments import record_payment
from billing.reports import monthly_revenue, tax_report

MARCH = date(2026, 3, 10)
DUE = date(2026, 4, 10)


def issued(book, on=MARCH):
    invoice = create_invoice(book, "C1", "JPY")
    add_line(book, invoice.invoice_id, "A", "商品A", "1000", 1, "0.10")
    add_line(book, invoice.invoice_id, "B", "商品B", "500", 1, "0.08")
    issue_invoice(book, invoice.invoice_id, "alice", on, DUE)
    return invoice


class MonthlyRevenueTest(unittest.TestCase):
    def test_counts_in_issue_month(self):
        book = Book()
        issued(book)
        issued(book, on=date(2026, 4, 1))
        self.assertEqual(monthly_revenue(book, 2026, 3), {"JPY": D("1500")})
        self.assertEqual(monthly_revenue(book, 2026, 4), {"JPY": D("1500")})
        self.assertEqual(monthly_revenue(book, 2026, 5), {})

    def test_refreshed_after_issue_and_void(self):
        book = Book()
        self.assertEqual(monthly_revenue(book, 2026, 3), {})
        invoice = issued(book)
        self.assertEqual(monthly_revenue(book, 2026, 3), {"JPY": D("1500")})
        void_invoice(book, invoice.invoice_id, "alice", date(2026, 3, 20))
        self.assertEqual(monthly_revenue(book, 2026, 3), {})

    def test_paid_invoice_stays_counted(self):
        book = Book()
        invoice = issued(book)
        record_payment(book, invoice.invoice_id, "1640", "cash", "alice", MARCH)
        self.assertEqual(monthly_revenue(book, 2026, 3), {"JPY": D("1500")})


class TaxReportTest(unittest.TestCase):
    def test_by_rate(self):
        book = Book()
        issued(book)
        issued(book)
        report = tax_report(book, 2026, 3)
        self.assertEqual(report["JPY"][D("0.10")], D("200"))
        self.assertEqual(report["JPY"][D("0.08")], D("80"))

    def test_invalidating_a_month_keeps_other_months(self):
        book = Book()
        issued(book)
        monthly_revenue(book, 2026, 3)
        monthly_revenue(book, 2026, 4)
        book.invalidate_report(2026, 4)
        self.assertIn(("revenue", 2026, 3), book.report_cache)
        self.assertNotIn(("revenue", 2026, 4), book.report_cache)


if __name__ == "__main__":
    unittest.main()
