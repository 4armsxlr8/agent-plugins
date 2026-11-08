"""追加の依頼 (reschedule) の採点。

- Basics: 依頼文に書いてあること
- CarriedOver: 元の判断のうち、コードを読めば引き継げるもの
- DocumentedOnly: 元の判断のうち、コードに現れにくいもの。支払い済みの回を含めて 12 回まで
"""

import json
import unittest
from datetime import date
from decimal import Decimal as D

from billing import store
from billing.book import Book
from billing.errors import BillingError, ValidationError
from billing.invoices import add_line, create_invoice, issue_invoice
from billing.payments import record_payment
from billing.pricing import balance_due, totals

from billing import installments as I

ISSUED = date(2026, 3, 10)
DUE = date(2026, 3, 31)
ON = date(2026, 4, 1)
FIRST = date(2026, 4, 15)
LATER_ON = date(2026, 5, 20)
NEW_FIRST = date(2026, 6, 15)  # 月曜。7/15 水, 8/14 は使わない


def started(price="12000", count=4, paid="3000"):
    book = Book()
    inv = create_invoice(book, "C1", "JPY")
    add_line(book, inv.invoice_id, "S", "x", price, 1, "0")
    issue_invoice(book, inv.invoice_id, "a", ISSUED, DUE)
    I.create_plan(book, inv.invoice_id, count, FIRST, "a", ON)
    if paid != "0":
        record_payment(book, inv.invoice_id, paid, "cash", "a", date(2026, 4, 10))
    return book, inv


class Basics(unittest.TestCase):
    def test_keeps_paid_and_renumbers(self):
        book, inv = started()
        rows = I.reschedule(book, inv.invoice_id, 3, NEW_FIRST, "a", LATER_ON)
        self.assertEqual([r.number for r in rows], [2, 3, 4])
        whole = I.schedule(book, inv.invoice_id)
        self.assertEqual([r.number for r in whole], [1, 2, 3, 4])
        self.assertEqual((whole[0].due_on, whole[0].amount, whole[0].remaining), (FIRST, D(3000), D(0)))
        self.assertEqual([r.amount for r in rows], [D(3000)] * 3)
        self.assertEqual(rows[0].due_on, NEW_FIRST)

    def test_partly_paid_row_closes_at_paid(self):
        book, inv = started(paid="4000")
        rows = I.reschedule(book, inv.invoice_id, 2, NEW_FIRST, "a", LATER_ON)
        whole = I.schedule(book, inv.invoice_id)
        self.assertEqual([(r.amount, r.remaining) for r in whole[:2]], [(D(3000), D(0)), (D(1000), D(0))])
        self.assertEqual([r.number for r in rows], [3, 4])
        self.assertEqual(sum(r.amount for r in rows), D(8000))

    def test_balances(self):
        book, inv = started(paid="4000")
        I.reschedule(book, inv.invoice_id, 3, NEW_FIRST, "a", LATER_ON)
        whole = I.schedule(book, inv.invoice_id)
        self.assertEqual(sum(r.remaining for r in whole), balance_due(inv))
        self.assertEqual(sum(r.amount for r in whole), totals(inv).total)

    def test_audit(self):
        book, inv = started()
        I.reschedule(book, inv.invoice_id, 3, NEW_FIRST, "a", LATER_ON)
        event = book.audit.of_kind("installment.plan_rescheduled")[-1]
        self.assertEqual((event.data["count"], event.data["amount"]), (3, "9000"))

    def test_persists(self):
        book, inv = started()
        I.reschedule(book, inv.invoice_id, 3, NEW_FIRST, "a", LATER_ON)
        loaded = store.load_book(json.loads(json.dumps(store.dump_book(book))))
        self.assertEqual([(r.number, r.due_on, r.amount, r.paid) for r in I.schedule(book, inv.invoice_id)],
                         [(r.number, r.due_on, r.amount, r.paid) for r in I.schedule(loaded, inv.invoice_id)])

    def test_payment_after_reschedule(self):
        book, inv = started()
        I.reschedule(book, inv.invoice_id, 3, NEW_FIRST, "a", LATER_ON)
        record_payment(book, inv.invoice_id, "3500", "cash", "a", date(2026, 5, 25))
        self.assertEqual([r.paid for r in I.schedule(book, inv.invoice_id)], [D(3000), D(3000), D(500), D(0)])

    def test_without_plan_rejected(self):
        book = Book()
        inv = create_invoice(book, "C1", "JPY")
        add_line(book, inv.invoice_id, "S", "x", "100", 1, "0")
        issue_invoice(book, inv.invoice_id, "a", ISSUED, DUE)
        with self.assertRaises(BillingError):
            I.reschedule(book, inv.invoice_id, 2, NEW_FIRST, "a", LATER_ON)


class CarriedOver(unittest.TestCase):
    def test_remainder_last(self):
        book, inv = started(price="10000", paid="2500")
        rows = I.reschedule(book, inv.invoice_id, 7, NEW_FIRST, "a", LATER_ON)
        self.assertEqual([r.amount for r in rows], [D(1071)] * 6 + [D(1074)])

    def test_window(self):
        book, inv = started()
        for bad in (LATER_ON, date(2026, 7, 20)):  # 当日と 61 日後
            with self.assertRaises(ValidationError):
                I.reschedule(book, inv.invoice_id, 2, bad, "a", LATER_ON)

    def test_month_end(self):
        book, inv = started()
        rows = I.reschedule(book, inv.invoice_id, 3, date(2026, 6, 30), "a", LATER_ON)
        self.assertEqual([r.due_on for r in rows], [date(2026, 6, 30), date(2026, 7, 31), date(2026, 8, 31)])

    def test_weekend(self):
        book, inv = started()
        rows = I.reschedule(book, inv.invoice_id, 2, date(2026, 6, 13), "a", LATER_ON)  # 土, 月
        self.assertEqual([r.due_on for r in rows], [date(2026, 6, 15), date(2026, 7, 13)])

    def test_tiny(self):
        book, inv = started(price="12", count=2, paid="6")
        with self.assertRaises(ValidationError):
            I.reschedule(book, inv.invoice_id, 7, NEW_FIRST, "a", LATER_ON)


class DocumentedOnly(unittest.TestCase):
    def test_limit_includes_paid_rows(self):
        book, inv = started(price="12000", count=4, paid="6000")  # 2 回分が済んでいる
        with self.assertRaises(ValidationError):
            I.reschedule(book, inv.invoice_id, 11, NEW_FIRST, "a", LATER_ON)
        rows = I.reschedule(book, inv.invoice_id, 10, NEW_FIRST, "a", LATER_ON)
        self.assertEqual(len(rows), 10)
