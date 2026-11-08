"""依頼者の判断によらず成り立つはずの性質。依頼者役には見せない。

- Conservation: 分けた額と入金の合計が請求書と合う
- Persistence: 保存と読み込みで分割が失われない
- UnawareCode: 分割を知らない既存の処理 (dataclasses.replace、集計、番号)
- Audit: 監査イベントの形
- Atomic: 失敗した操作が何も残さない
- Statement: 明細書の項目
- Overdue: 督促の土台 (猶予よりずっと後の日で確かめる)

判断によらないと言い切れないものが 2 つある。入金を古い回から充てること (判断 PaymentOldest) は Statement と Overdue の一部が、
元の期日を残すこと (判断 DueOnKept) は取りやめ後の期日を見るテストが前提にしている。
"""

import json
import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal as D

from billing import store
from billing.book import Book
from billing.errors import BillingError, ValidationError
from billing.invoices import add_line, create_invoice, duplicate_invoice, issue_invoice, set_allowance, void_invoice
from billing.payments import record_payment
from billing.pricing import balance_due, paid_total, totals
from billing.receivables import customer_statement, customer_summary, overdue_amount, overdue_invoices
from billing.reports import monthly_revenue, tax_report

try:
    from billing import installments as I
except ImportError:
    I = None

ISSUED = date(2026, 3, 10)
DUE = date(2026, 3, 31)
ON = date(2026, 4, 1)
FIRST = date(2026, 4, 15)
FAR = date(2026, 5, 1)  # 1 回目の猶予は過ぎ、2 回目 (5/15) の期日より前


def invoice(book, lines=(("3000", 1, "0.10"),), allowance="0", currency="JPY", customer="C1"):
    inv = create_invoice(book, customer, currency)
    for price, qty, rate in lines:
        add_line(book, inv.invoice_id, "S", "x", price, qty, rate)
    if allowance != "0":
        set_allowance(book, inv.invoice_id, allowance)
    issue_invoice(book, inv.invoice_id, "a", ISSUED, DUE)
    return inv


def pay(book, inv, amount, on=date(2026, 4, 5)):
    return record_payment(book, inv.invoice_id, amount, "cash", "a", on)


class Conservation(unittest.TestCase):
    def test_sum_equals_balance(self):
        cases = [
            (("3000", 1, "0.10"),), (("1005", 2, "0.10"), ("333", 3, "0.08")), (("9999", 7, "0.08"),),
        ]
        for lines in cases:
            for count in (2, 3, 7, 11, 12):
                book = Book()
                inv = invoice(book, lines)
                plan = I.create_plan(book, inv.invoice_id, count, FIRST, "a", ON)
                self.assertEqual(sum(p.amount for p in plan), totals(inv).total)

    def test_usd_units(self):
        book = Book()
        inv = invoice(book, (("100.33", 1, "0.10"),), currency="USD")
        plan = I.create_plan(book, inv.invoice_id, 7, FIRST, "a", ON)
        self.assertEqual(sum(p.amount for p in plan), totals(inv).total)
        for p in plan:
            self.assertEqual(p.amount.quantize(D("0.01")), p.amount)

    def test_after_allowance(self):
        book = Book()
        inv = invoice(book, (("1000", 3, "0.10"), ("500", 1, "0.08")), allowance="7")
        plan = I.create_plan(book, inv.invoice_id, 5, FIRST, "a", ON)
        self.assertEqual(sum(p.amount for p in plan), balance_due(inv))

    def test_remaining_tracks_balance(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        for amount in ("100", "1500", "400"):
            pay(book, inv, amount)
            rows = I.schedule(book, inv.invoice_id)
            self.assertEqual(sum(r.remaining for r in rows), balance_due(inv))
            self.assertEqual(sum(r.paid for r in rows), paid_total(inv))
            for r in rows:
                self.assertEqual(r.paid + r.remaining, r.amount)

    def test_full_payment_clears_all(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        pay(book, inv, totals(inv).total)
        self.assertEqual(book.get_invoice(inv.invoice_id).status, "paid")
        self.assertTrue(all(r.remaining == 0 for r in I.schedule(book, inv.invoice_id)))

    def test_fractional_total_either_rejected_or_conserved(self):
        # 単価に端数のある請求書は請求額が最小単位で表せない。拒否するなら拒否でよく、受けるなら合計が合うこと
        book = Book()
        inv = invoice(book, (("10.5", 1, "0"),))
        try:
            plan = I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        except BillingError:
            return
        self.assertEqual(sum(p.amount for p in plan), totals(inv).total)


class Persistence(unittest.TestCase):
    def roundtrip(self, book):
        return store.load_book(json.loads(json.dumps(store.dump_book(book))))

    def test_plan_survives(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        pay(book, inv, "1500")
        loaded = self.roundtrip(book)
        before, after = I.schedule(book, inv.invoice_id), I.schedule(loaded, inv.invoice_id)
        self.assertEqual([(r.number, r.due_on, r.amount, r.paid, r.remaining) for r in before],
                         [(r.number, r.due_on, r.amount, r.paid, r.remaining) for r in after])

    def test_payment_after_load_is_allocated(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        loaded = self.roundtrip(book)
        record_payment(loaded, inv.invoice_id, "1100", "cash", "a", date(2026, 4, 5))
        self.assertEqual(sum(r.paid for r in I.schedule(loaded, inv.invoice_id)), D(1100))

    def test_partial_before_plan_survives(self):
        book = Book()
        inv = invoice(book)
        pay(book, inv, "300", date(2026, 3, 20))
        try:
            I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        except BillingError:
            return  # 一部入金済みを分割できるかは判断 PartialAllowed で採点する
        loaded = self.roundtrip(book)
        self.assertEqual([r.paid for r in I.schedule(loaded, inv.invoice_id)], [D(0)] * 3)

    def test_cancelled_stays_cancelled(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        I.cancel_plan(book, inv.invoice_id, "a", ON)
        self.assertEqual(list(I.schedule(self.roundtrip(book), inv.invoice_id)), [])

    def test_file_without_plan_still_loads(self):
        # 変更前のコードが保存した形。分割の項目が無い
        data = {"schema_version": 1, "counters": {"invoice": 1, "payment": 0}, "audit": [], "invoices": [{
            "invoice_id": "INV-0001", "customer_id": "C1", "currency": "JPY",
            "lines": [{"line_id": "L1", "sku": "S", "description": "x", "unit_price": "100", "quantity": 1, "tax_rate": "0"}],
            "allowance": "0", "status": "issued", "issued_on": "2026-03-10", "due_on": "2026-03-31", "payments": [], "memo": "",
        }]}
        loaded = store.load_book(data)
        self.assertEqual(list(I.schedule(loaded, "INV-0001")), [])

    def test_save_file(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "b.json")
            store.save(book, path)
            self.assertEqual(len(I.schedule(store.load(path), inv.invoice_id)), 3)


class UnawareCode(unittest.TestCase):
    def test_duplicate_has_no_plan(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        copy = duplicate_invoice(book, inv.invoice_id)
        self.assertEqual(list(I.schedule(book, copy.invoice_id)), [])
        add_line(book, copy.invoice_id, "S", "y", "100", 1, "0")
        issue_invoice(book, copy.invoice_id, "a", date(2026, 4, 2), date(2026, 4, 30))
        self.assertEqual(len(I.create_plan(book, copy.invoice_id, 2, FIRST, "a", date(2026, 4, 2))), 2)
        self.assertEqual(len(I.schedule(book, inv.invoice_id)), 3)

    def test_summary_and_reports_unchanged(self):
        book = Book()
        inv = invoice(book)
        summary = customer_summary(book, "C1")
        revenue, tax = monthly_revenue(book, 2026, 3), tax_report(book, 2026, 3)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        self.assertEqual({k: summary["JPY"][k] for k in ("billed", "paid", "outstanding", "invoice_count")},
                         {k: customer_summary(book, "C1")["JPY"][k] for k in ("billed", "paid", "outstanding", "invoice_count")})
        self.assertEqual((revenue, tax), (monthly_revenue(book, 2026, 3), tax_report(book, 2026, 3)))

    def test_only_open_invoices(self):
        book = Book()
        draft = create_invoice(book, "C1", "JPY")
        with self.assertRaises(BillingError):
            I.create_plan(book, draft.invoice_id, 3, FIRST, "a", ON)
        paid = invoice(book)
        pay(book, paid, totals(paid).total)
        with self.assertRaises(BillingError):
            I.create_plan(book, paid.invoice_id, 3, FIRST, "a", ON)
        void = invoice(book)
        void_invoice(book, void.invoice_id, "a", ON)
        with self.assertRaises(BillingError):
            I.create_plan(book, void.invoice_id, 3, FIRST, "a", ON)

    def test_second_plan_is_not_silently_stacked(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        try:
            I.create_plan(book, inv.invoice_id, 2, FIRST, "a", ON)
        except BillingError:
            self.assertEqual(len(I.schedule(book, inv.invoice_id)), 3)
            return
        self.assertEqual(len(I.schedule(book, inv.invoice_id)), 2)
        self.assertEqual(sum(r.amount for r in I.schedule(book, inv.invoice_id)), totals(inv).total)

    def test_cancel_without_plan_changes_nothing(self):
        # 拒否しても何もしなくてもよい。無い分割を取りやめた記録を残さない
        book = Book()
        inv = invoice(book)
        audit = len(book.audit.to_list())
        try:
            I.cancel_plan(book, inv.invoice_id, "a", ON)
        except BillingError:
            pass
        self.assertEqual(len(book.audit.to_list()), audit)
        self.assertEqual(list(I.schedule(book, inv.invoice_id)), [])

    def test_not_integer_count_rejected(self):
        book = Book()
        inv = invoice(book)
        with self.assertRaises((ValidationError, TypeError)):
            I.create_plan(book, inv.invoice_id, 2.5, FIRST, "a", ON)


class Audit(unittest.TestCase):
    def test_created_and_cancelled(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        I.cancel_plan(book, inv.invoice_id, "a", ON)
        kinds = [e for e in book.audit.to_list() if "installment" in json.dumps(e)]
        self.assertEqual(len(kinds), 2)
        text = json.dumps(kinds, ensure_ascii=False)
        self.assertIn("installment.plan_created", text)
        self.assertIn("installment.plan_cancelled", text)
        self.assertIn('"3300"', text)  # format_amount の形
        json.dumps(store.dump_book(book))

    def test_usd_amount_format(self):
        book = Book()
        inv = invoice(book, (("100.00", 1, "0"),), currency="USD")
        I.create_plan(book, inv.invoice_id, 2, FIRST, "a", ON)
        self.assertIn('"100.00"', json.dumps(book.audit.to_list()))


class Atomic(unittest.TestCase):
    def test_failed_create_leaves_nothing(self):
        book = Book()
        inv = invoice(book)
        audit = len(book.audit.to_list())
        dumped = store.dump_book(book)
        with self.assertRaises(ValidationError):
            I.create_plan(book, inv.invoice_id, 0, FIRST, "a", ON)
        self.assertEqual(len(book.audit.to_list()), audit)
        self.assertEqual(list(I.schedule(book, inv.invoice_id)), [])
        self.assertEqual(store.dump_book(book), dumped)


class Statement(unittest.TestCase):
    def rows(self, book):
        return {r["invoice_id"]: r for r in customer_statement(book, "C1")}

    def test_without_plan(self):
        book = Book()
        inv = invoice(book)
        row = self.rows(book)[inv.invoice_id]
        self.assertEqual((row["next_due_on"], row["next_due_amount"]), (DUE, totals(inv).total))

    def test_with_plan_after_payment(self):
        book = Book()
        inv = invoice(book, (("3000", 1, "0"),))
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        row = self.rows(book)[inv.invoice_id]
        self.assertEqual((row["next_due_on"], row["next_due_amount"]), (FIRST, D(1000)))
        pay(book, inv, "1300")
        row = self.rows(book)[inv.invoice_id]
        self.assertEqual(row["next_due_amount"], D(700))
        self.assertEqual(row["next_due_on"], I.schedule(book, inv.invoice_id)[1].due_on)

    def test_paid(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        pay(book, inv, totals(inv).total)
        row = self.rows(book)[inv.invoice_id]
        self.assertEqual((row["next_due_on"], row["next_due_amount"]), (None, None))

    def test_after_cancel_back_to_invoice(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        I.cancel_plan(book, inv.invoice_id, "a", ON)
        row = self.rows(book)[inv.invoice_id]
        self.assertEqual((row["next_due_on"], row["next_due_amount"]), (DUE, totals(inv).total))


class Overdue(unittest.TestCase):
    def test_plan_defers_original_due(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        self.assertEqual(overdue_invoices(book, date(2026, 4, 2)), [])  # 元の期日 3/31 は過ぎている

    def test_paid_installment_not_overdue(self):
        book = Book()
        inv = invoice(book, (("3000", 1, "0"),))
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        pay(book, inv, "1000")
        self.assertEqual(overdue_invoices(book, FAR), [])
        self.assertEqual(overdue_amount(book, "C1", FAR), {})

    def test_cancel_restores_original_due(self):
        book = Book()
        inv = invoice(book)
        I.create_plan(book, inv.invoice_id, 3, FIRST, "a", ON)
        I.cancel_plan(book, inv.invoice_id, "a", ON)
        self.assertEqual([x.invoice_id for x in overdue_invoices(book, date(2026, 4, 2))], [inv.invoice_id])

    def test_plain_invoice_unchanged_next_to_plan(self):
        book = Book()
        planned = invoice(book)
        plain = invoice(book)
        I.create_plan(book, planned.invoice_id, 3, FIRST, "a", ON)
        self.assertEqual([x.invoice_id for x in overdue_invoices(book, date(2026, 4, 2))], [plain.invoice_id])
