import json
import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal as D

from billing.book import Book
from billing.errors import StoreError
from billing.invoices import add_line, create_invoice, issue_invoice, set_allowance
from billing.payments import record_payment
from billing.pricing import totals
from billing.store import dump_book, load, load_book, save

ON = date(2026, 3, 10)
DUE = date(2026, 4, 10)


def sample_book():
    book = Book()
    invoice = create_invoice(book, "C1", "USD", memo="初回")
    add_line(book, invoice.invoice_id, "A", "商品A", "19.99", 3, "0.10")
    set_allowance(book, invoice.invoice_id, "0.49")
    issue_invoice(book, invoice.invoice_id, "alice", ON, DUE)
    record_payment(book, invoice.invoice_id, "10.00", "card", "alice", ON)
    return book, invoice


class StoreTest(unittest.TestCase):
    def test_dump_is_stable_through_load(self):
        book, _ = sample_book()
        data = json.loads(json.dumps(dump_book(book)))
        self.assertEqual(dump_book(load_book(data)), data)

    def test_save_and_load_file(self):
        book, invoice = sample_book()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "book.json")
            save(book, path)
            loaded = load(path)
        restored = loaded.get_invoice(invoice.invoice_id)
        self.assertEqual(restored.lines[0].unit_price, D("19.99"))
        self.assertEqual(restored.allowance, D("0.49"))
        self.assertEqual(restored.issued_on, ON)
        self.assertEqual(restored.payments[0].amount, D("10.00"))
        self.assertEqual(totals(restored).total, totals(invoice).total)
        self.assertEqual(restored.memo, "初回")
        self.assertEqual(len(loaded.audit.events), len(book.audit.events))

    def test_numbers_continue_after_load(self):
        book, _ = sample_book()
        loaded = load_book(json.loads(json.dumps(dump_book(book))))
        self.assertEqual(loaded.next_id("invoice"), "INV-0002")
        self.assertEqual(loaded.next_id("payment"), "PAY-0002")

    def test_unknown_schema_version(self):
        with self.assertRaises(StoreError):
            load_book({"schema_version": 999})

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(StoreError):
                load(os.path.join(tmp, "missing.json"))


if __name__ == "__main__":
    unittest.main()
