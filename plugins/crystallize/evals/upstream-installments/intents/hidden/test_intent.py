"""依頼者の判断 12 件を 1 クラスずつ確かめる。クラス名が判断の名前。

あるクラスが別の判断に引きずられて落ちないよう、割り切れる額と平日の期日を使い、回の金額に端数を出さない。
"""

import unittest
from datetime import date, timedelta
from decimal import Decimal as D

from billing.book import Book
from billing.errors import BillingError, ValidationError
from billing.invoices import add_line, create_invoice, issue_invoice, void_invoice
from billing.payments import record_payment
from billing.receivables import overdue_amount, overdue_invoices

try:
    from billing import installments as I
except ImportError:
    I = None

ISSUED = date(2026, 3, 10)
DUE = date(2026, 3, 31)
ON = date(2026, 4, 1)
FIRST = date(2026, 4, 15)  # 水曜。5/15 金、6/15 月
RATE = D("0")


def invoice(book, price="3000", currency="JPY"):
    inv = create_invoice(book, "C1", currency)
    add_line(book, inv.invoice_id, "S", "x", price, 1, RATE)
    issue_invoice(book, inv.invoice_id, "a", ISSUED, DUE)
    return inv


def pay(book, inv, amount, on=date(2026, 4, 5)):
    return record_payment(book, inv.invoice_id, amount, "cash", "a", on)


class CountLimit(unittest.TestCase):
    def test_range(self):
        for bad in (1, 13):
            book = Book()
            inv = invoice(book)
            with self.assertRaises(ValidationError):
                I.create_plan(book, inv.invoice_id, bad, FIRST, "a", ON)
        for good in (2, 12):
            book = Book()
            inv = invoice(book, "12000")
            self.assertEqual(len(I.create_plan(book, inv.invoice_id, good, FIRST, "a", ON)), good)


class RemainderLast(unittest.TestCase):
    def test_last(self):
        book = Book()
        inv = invoice(book, "100")
        plan = I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        self.assertEqual([p.amount for p in plan], [D(33), D(33), D(34)])

    def test_usd(self):
        book = Book()
        inv = invoice(book, "10.00", "USD")
        plan = I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        self.assertEqual([p.amount for p in plan], [D("3.33"), D("3.33"), D("3.34")])


class Grace(unittest.TestCase):
    def setUp(self):
        self.book = Book()
        self.inv = invoice(self.book)
        I.create_plan(self.book, self.inv.invoice_id, 3, FIRST, "a", ON)

    def test_within_grace(self):
        self.assertEqual(overdue_invoices(self.book, FIRST + timedelta(days=7)), [])

    def test_after_grace(self):
        self.assertEqual([x.invoice_id for x in overdue_invoices(self.book, FIRST + timedelta(days=8))], [self.inv.invoice_id])
        self.assertEqual(overdue_amount(self.book, "C1", FIRST + timedelta(days=8)), {"JPY": D(1000)})

    def test_second_within_grace_not_counted(self):
        as_of = date(2026, 5, 22)  # 5/15 の 7 日後
        self.assertEqual(overdue_amount(self.book, "C1", as_of), {"JPY": D(1000)})


class PartialAllowed(unittest.TestCase):
    def test_splits_balance(self):
        book = Book()
        inv = invoice(book)
        pay(book, inv, "600", date(2026, 3, 20))
        plan = I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        self.assertEqual([p.amount for p in plan], [D(800)] * 3)
        self.assertEqual([p.paid for p in plan], [D(0)] * 3)


class FirstDueWindow(unittest.TestCase):
    def test_bounds(self):
        for bad in (ON, ON - timedelta(days=1), ON + timedelta(days=61)):
            book = Book()
            inv = invoice(book)
            with self.assertRaises(ValidationError):
                I.create_plan(book, inv.invoice_id, 3, bad, "a", ON)
        book = Book()
        inv = invoice(book)
        self.assertEqual(len(I.create_plan(book, inv.invoice_id, 3, ON + timedelta(days=1), "a", ON)), 3)

    def test_day_60(self):
        book = Book()
        inv = invoice(book)
        on = date(2026, 3, 16)  # 60 日後は 5/15 金
        self.assertEqual(len(I.create_plan(book, inv.invoice_id, 3, on + timedelta(days=60), "a", on)), 3)


class PaymentOldest(unittest.TestCase):
    def test_oldest_first(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        pay(book, inv, "1500")
        rows = I.schedule(book, inv.invoice_id)
        self.assertEqual([r.paid for r in rows], [D(1000), D(500), D(0)])
        self.assertEqual([r.remaining for r in rows], [D(0), D(500), D(1000)])


class DueOnKept(unittest.TestCase):
    def test_kept(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        self.assertEqual(book.get_invoice(inv.invoice_id).due_on, DUE)


class MonthEnd(unittest.TestCase):
    def test_always_month_end(self):
        book = Book()
        inv = invoice(book, "4000")
        on = date(2026, 6, 1)
        plan = I.create_plan(book, inv.invoice_id, 4, date(2026, 6, 30), "a", on)  # 火, 金, 月, 水
        self.assertEqual([p.due_on for p in plan], [date(2026, 6, 30), date(2026, 7, 31), date(2026, 8, 31), date(2026, 9, 30)])


class VoidBlocked(unittest.TestCase):
    def test_blocked_until_cancelled(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        with self.assertRaises(BillingError):
            void_invoice(book, inv.invoice_id, "a", date(2026, 4, 2))
        I.cancel_plan(book, inv.invoice_id, "a", date(2026, 4, 2))
        void_invoice(book, inv.invoice_id, "a", date(2026, 4, 3))
        self.assertEqual(book.get_invoice(inv.invoice_id).status, "void")


class PaidCancelBlocked(unittest.TestCase):
    def test_payment_after_plan_blocks(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        pay(book, inv, "100")
        with self.assertRaises(BillingError):
            I.cancel_plan(book, inv.invoice_id, "a", date(2026, 4, 6))

    def test_payment_before_plan_does_not_block(self):
        book = Book()
        inv = invoice(book)
        pay(book, inv, "600", date(2026, 3, 20))
        try:
            I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        except BillingError:
            return  # 一部入金済みを分割できるかは PartialAllowed で採点する
        I.cancel_plan(book, inv.invoice_id, "a", date(2026, 4, 6))
        self.assertEqual(list(I.schedule(book, inv.invoice_id)), [])


class TinyRejected(unittest.TestCase):
    def test_zero_installment_rejected(self):
        book = Book()
        inv = invoice(book, "5")
        with self.assertRaises(ValidationError):
            I.create_plan(book, inv.invoice_id, 6, FIRST, "a", ON)
        self.assertEqual(list(I.schedule(book, inv.invoice_id)), [])

    def test_one_each_allowed(self):
        book = Book()
        inv = invoice(book, "6")
        self.assertEqual([p.amount for p in I.create_plan(book, inv.invoice_id, 6, FIRST, "a", ON)], [D(1)] * 6)


class WeekendShift(unittest.TestCase):
    def test_saturday_to_monday(self):
        book = Book()
        inv = invoice(book)
        on = date(2026, 7, 20)
        plan = I.create_plan(book, inv.invoice_id, 3, date(2026, 8, 15), "a", on)  # 土, 火, 木
        self.assertEqual([p.due_on for p in plan], [date(2026, 8, 17), date(2026, 9, 15), date(2026, 10, 15)])
