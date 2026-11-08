import unittest
from datetime import date
from decimal import Decimal as D

from billing.book import Book
from billing.errors import InvalidTransition, ValidationError
from billing.invoices import add_line, create_invoice, issue_invoice
from billing.models import PAID, PARTIALLY_PAID
from billing.payments import record_payment
from billing.pricing import balance_due

ON = date(2026, 3, 10)
DUE = date(2026, 4, 10)


def issued(book, currency="JPY", price="1000"):
    invoice = create_invoice(book, "C1", currency)
    add_line(book, invoice.invoice_id, "A", "商品A", price, 1, "0.10")
    issue_invoice(book, invoice.invoice_id, "alice", ON, DUE)
    return invoice


class RecordPaymentTest(unittest.TestCase):
    def test_partial_then_full(self):
        book = Book()
        invoice = issued(book)
        record_payment(book, invoice.invoice_id, "400", "cash", "alice", ON)
        self.assertEqual(invoice.status, PARTIALLY_PAID)
        self.assertEqual(balance_due(invoice), D("700"))
        record_payment(book, invoice.invoice_id, "700", "card", "alice", ON)
        self.assertEqual(invoice.status, PAID)
        self.assertEqual(balance_due(invoice), D("0"))

    def test_events_are_recorded_payment_first(self):
        book = Book()
        invoice = issued(book, currency="USD", price="10.00")
        record_payment(book, invoice.invoice_id, "11.00", "card", "bob", ON)
        kinds = [e.kind for e in book.audit.for_invoice(invoice.invoice_id)]
        self.assertEqual(kinds[-2:], ["payment.recorded", "invoice.status_changed"])
        payment_event = book.audit.of_kind("payment.recorded")[0]
        self.assertEqual(payment_event.data["amount"], "11.00")
        self.assertEqual(payment_event.actor, "bob")

    def test_second_partial_payment_has_no_status_event(self):
        book = Book()
        invoice = issued(book)
        record_payment(book, invoice.invoice_id, "100", "cash", "alice", ON)
        before = len(book.audit.of_kind("invoice.status_changed"))
        record_payment(book, invoice.invoice_id, "100", "cash", "alice", ON)
        self.assertEqual(len(book.audit.of_kind("invoice.status_changed")), before)

    def test_overpayment_is_rejected(self):
        book = Book()
        invoice = issued(book)
        with self.assertRaises(ValidationError):
            record_payment(book, invoice.invoice_id, "1101", "cash", "alice", ON)

    def test_failed_payment_does_not_consume_number(self):
        book = Book()
        invoice = issued(book)
        with self.assertRaises(ValidationError):
            record_payment(book, invoice.invoice_id, "1101", "cash", "alice", ON)
        payment = record_payment(book, invoice.invoice_id, "100", "cash", "alice", ON)
        self.assertEqual(payment.payment_id, "PAY-0001")

    def test_paid_invoice_rejects_payment(self):
        book = Book()
        invoice = issued(book)
        record_payment(book, invoice.invoice_id, "1100", "cash", "alice", ON)
        with self.assertRaises(InvalidTransition):
            record_payment(book, invoice.invoice_id, "1", "cash", "alice", ON)

    def test_unknown_method(self):
        book = Book()
        invoice = issued(book)
        with self.assertRaises(ValidationError):
            record_payment(book, invoice.invoice_id, "1", "barter", "alice", ON)


if __name__ == "__main__":
    unittest.main()
