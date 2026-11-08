import unittest
from datetime import date
from decimal import Decimal as D

from billing.book import Book
from billing.invoices import add_line, create_invoice, issue_invoice, void_invoice
from billing.payments import record_payment
from billing.receivables import customer_statement, customer_summary, overdue_amount, overdue_invoices

ON = date(2026, 3, 10)
DUE = date(2026, 4, 10)


def issued(book, customer="C1", price="1000", due=DUE):
    invoice = create_invoice(book, customer, "JPY")
    add_line(book, invoice.invoice_id, "A", "商品A", price, 1, "0.10")
    issue_invoice(book, invoice.invoice_id, "alice", ON, due)
    return invoice


class CustomerSummaryTest(unittest.TestCase):
    def test_counts_issued_and_paid(self):
        book = Book()
        first = issued(book)
        issued(book)
        record_payment(book, first.invoice_id, "1100", "cash", "alice", ON)
        row = customer_summary(book, "C1")["JPY"]
        self.assertEqual(row["billed"], D("2200"))
        self.assertEqual(row["paid"], D("1100"))
        self.assertEqual(row["outstanding"], D("1100"))
        self.assertEqual(row["invoice_count"], 2)

    def test_summary_is_refreshed_after_payment(self):
        book = Book()
        invoice = issued(book)
        self.assertEqual(customer_summary(book, "C1")["JPY"]["paid"], D("0"))
        record_payment(book, invoice.invoice_id, "100", "cash", "alice", ON)
        self.assertEqual(customer_summary(book, "C1")["JPY"]["paid"], D("100"))

    def test_void_is_not_counted(self):
        book = Book()
        invoice = issued(book)
        self.assertEqual(customer_summary(book, "C1")["JPY"]["invoice_count"], 1)
        void_invoice(book, invoice.invoice_id, "alice", ON)
        self.assertEqual(customer_summary(book, "C1"), {})

    def test_returned_summary_is_a_copy(self):
        book = Book()
        issued(book)
        customer_summary(book, "C1")["JPY"]["billed"] = D("0")
        self.assertEqual(customer_summary(book, "C1")["JPY"]["billed"], D("1100"))


class OverdueTest(unittest.TestCase):
    def test_overdue_excludes_paid_and_not_yet_due(self):
        book = Book()
        late = issued(book, due=date(2026, 3, 20))
        issued(book, due=date(2026, 5, 1))
        paid = issued(book, due=date(2026, 3, 20))
        record_payment(book, paid.invoice_id, "1100", "cash", "alice", ON)
        found = overdue_invoices(book, date(2026, 4, 1))
        self.assertEqual([inv.invoice_id for inv in found], [late.invoice_id])

    def test_partially_paid_stays_overdue(self):
        book = Book()
        invoice = issued(book, due=date(2026, 3, 20))
        record_payment(book, invoice.invoice_id, "100", "cash", "alice", ON)
        self.assertEqual(overdue_amount(book, "C1", date(2026, 4, 1)), {"JPY": D("1000")})


class StatementTest(unittest.TestCase):
    def test_statement_rows(self):
        book = Book()
        invoice = issued(book)
        create_invoice(book, "C1", "JPY")
        rows = customer_statement(book, "C1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["invoice_id"], invoice.invoice_id)
        self.assertEqual(rows[0]["total"], D("1100"))


if __name__ == "__main__":
    unittest.main()
