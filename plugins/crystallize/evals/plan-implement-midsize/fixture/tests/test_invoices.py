import unittest
from datetime import date
from decimal import Decimal as D

from billing.book import Book
from billing.errors import InvalidTransition, ValidationError
from billing.invoices import (
    add_line,
    amend_quantities,
    create_invoice,
    duplicate_invoice,
    issue_invoice,
    remove_line,
    set_allowance,
    void_invoice,
)
from billing.models import DRAFT, ISSUED, VOID
from billing.payments import record_payment
from billing.pricing import totals

ON = date(2026, 3, 10)
DUE = date(2026, 4, 10)


def draft(book):
    invoice = create_invoice(book, "C1", "JPY")
    add_line(book, invoice.invoice_id, "A", "商品A", "1000", 3, "0.10")
    add_line(book, invoice.invoice_id, "B", "商品B", "500", 2, "0.08")
    return invoice


class DraftEditTest(unittest.TestCase):
    def test_line_ids_are_sequential(self):
        invoice = draft(Book())
        self.assertEqual([line.line_id for line in invoice.lines], ["L1", "L2"])

    def test_line_id_not_reused_after_removing_the_middle(self):
        book = Book()
        invoice = draft(book)
        remove_line(book, invoice.invoice_id, "L1")
        self.assertEqual(add_line(book, invoice.invoice_id, "C", "商品C", "1", 1, "0.10").line_id, "L3")

    def test_amend_quantities(self):
        book = Book()
        invoice = draft(book)
        amend_quantities(book, invoice.invoice_id, {"L1": 2, "L2": -1})
        self.assertEqual([line.quantity for line in invoice.lines], [5, 1])

    def test_amend_rejects_non_positive_result_without_partial_change(self):
        book = Book()
        invoice = draft(book)
        with self.assertRaises(ValidationError):
            amend_quantities(book, invoice.invoice_id, {"L1": 2, "L2": -2})
        self.assertEqual([line.quantity for line in invoice.lines], [3, 2])

    def test_allowance_cannot_exceed_subtotal(self):
        book = Book()
        invoice = draft(book)
        with self.assertRaises(ValidationError):
            set_allowance(book, invoice.invoice_id, "4001")

    def test_issued_invoice_cannot_be_edited(self):
        book = Book()
        invoice = draft(book)
        issue_invoice(book, invoice.invoice_id, "alice", ON, DUE)
        with self.assertRaises(InvalidTransition):
            add_line(book, invoice.invoice_id, "C", "商品C", "1", 1, "0.10")


class IssueAndVoidTest(unittest.TestCase):
    def test_issue(self):
        book = Book()
        invoice = draft(book)
        issue_invoice(book, invoice.invoice_id, "alice", ON, DUE)
        self.assertEqual(invoice.status, ISSUED)
        self.assertEqual(invoice.issued_on, ON)
        event = book.audit.of_kind("invoice.status_changed")[-1]
        self.assertEqual(event.data, {"from": DRAFT, "to": ISSUED})
        self.assertEqual(event.actor, "alice")
        self.assertEqual(event.at, "2026-03-10")

    def test_empty_invoice_cannot_be_issued(self):
        book = Book()
        invoice = create_invoice(book, "C1", "JPY")
        with self.assertRaises(ValidationError):
            issue_invoice(book, invoice.invoice_id, "alice", ON, DUE)

    def test_void_issued(self):
        book = Book()
        invoice = draft(book)
        issue_invoice(book, invoice.invoice_id, "alice", ON, DUE)
        void_invoice(book, invoice.invoice_id, "alice", ON)
        self.assertEqual(invoice.status, VOID)

    def test_void_with_payment_is_rejected(self):
        book = Book()
        invoice = draft(book)
        issue_invoice(book, invoice.invoice_id, "alice", ON, DUE)
        record_payment(book, invoice.invoice_id, "100", "cash", "alice", ON)
        with self.assertRaises(InvalidTransition):
            void_invoice(book, invoice.invoice_id, "alice", ON)


class DuplicateTest(unittest.TestCase):
    def test_duplicate_starts_as_new_draft_without_payments(self):
        book = Book()
        invoice = draft(book)
        set_allowance(book, invoice.invoice_id, "100")
        issue_invoice(book, invoice.invoice_id, "alice", ON, DUE)
        record_payment(book, invoice.invoice_id, "100", "cash", "alice", ON)

        copy = duplicate_invoice(book, invoice.invoice_id)

        self.assertNotEqual(copy.invoice_id, invoice.invoice_id)
        self.assertEqual(copy.status, DRAFT)
        self.assertEqual(copy.payments, [])
        self.assertIsNone(copy.issued_on)
        self.assertEqual(totals(copy).total, D("4270"))

    def test_duplicate_lines_are_independent(self):
        book = Book()
        invoice = draft(book)
        copy = duplicate_invoice(book, invoice.invoice_id)
        amend_quantities(book, copy.invoice_id, {"L1": 1})
        self.assertEqual(invoice.line("L1").quantity, 3)


if __name__ == "__main__":
    unittest.main()
