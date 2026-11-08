"""部分返金の隠しテスト。

クラス名が落ちた原因の分類になっている。
- Trap1Persistence: 保存処理が項目を明示的に列挙している (返金・番号カウンタ・変更前の形式)
- Trap2Cache: 集計キャッシュの無効化 (入金は顧客の残高しか捨てない。月次は返金日の月を捨てる)
- Trap3Rounding: 値引きの按分・四捨五入と切り捨ての使い分け・税率ごとの累計・通貨の桁
- Trap4CallerInput: 既存の normalize_quantities は渡した dict をその場で書き換える
- Trap5Audit: transition 経由の状態変更・同じ状態への遷移の禁止・data の金額の表現・イベントの順
- Trap6UnawareCode: 新しい状態と新しい項目を知らない既存の処理 (状態の列挙と dataclasses.replace)
- Basics: 罠ではない入力の検査
- SpecBeyondTable: spec にあり受け入れ基準表の例では確かめきれない点。表をなぞるだけでは通らない
- Preserved: plan の「守るべき既存挙動」。返金を呼ぶ test_refunded_invoice_rejects_payment 以外は未変更の fixture でも通る

コメントは各テストの対応先 (spec の AC・要件・スコープ外 / plan の守るべき既存挙動)。
"""

import json
import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal as D

import billing
from billing import store
from billing.book import Book
from billing.errors import InvalidTransition, NotFound, ValidationError
from billing.invoices import add_line, create_invoice, duplicate_invoice, issue_invoice, set_allowance
from billing.payments import record_payment
from billing.pricing import totals
from billing.receivables import customer_statement, customer_summary, overdue_invoices
from billing.reports import monthly_revenue, tax_report, taxable_base_report

try:
    from billing import refunds as R
except ImportError:
    R = None  # 無ければ機能テストはそれぞれ AttributeError で落ちる

ISSUED_ON = date(2026, 3, 10)
PAID_ON = date(2026, 3, 20)
DUE_ON = date(2026, 3, 31)
ON = date(2026, 4, 15)
RATE10 = D("0.10")
RATE8 = D("0.08")


def paid_invoice(book, lines, allowance="0", currency="JPY", customer="C1"):
    invoice = create_invoice(book, customer, currency)
    for price, quantity, rate in lines:
        add_line(book, invoice.invoice_id, "SKU", "商品", price, quantity, rate)
    set_allowance(book, invoice.invoice_id, allowance)
    issue_invoice(book, invoice.invoice_id, "alice", ISSUED_ON, DUE_ON)
    record_payment(book, invoice.invoice_id, totals(invoice).total, "bank_transfer", "alice", PAID_ON)
    return invoice


def invoice_a(book):
    return paid_invoice(book, [("1000", 3, "0.10"), ("500", 2, "0.08")], allowance="100")


def invoice_b(book):
    return paid_invoice(book, [("25", 2, "0.10")], allowance="25")


def invoice_c(book):
    return paid_invoice(book, [("15", 1, "0.10"), ("15", 1, "0.10")])


def invoice_d(book):
    return paid_invoice(book, [("10.25", 2, "0.10")], allowance="0.49", currency="USD")


def invoice_e(book):
    return paid_invoice(book, [("1000", 3, "0.10"), ("500", 2, "0.08")])


def refund(book, invoice, quantities, on=ON, reason="返品", actor="alice"):
    return R.issue_refund(book, invoice.invoice_id, quantities, reason, actor, on)


def refund_list(book, invoice):
    return list(R.refunds_for(book, invoice.invoice_id))


def reload_book(book):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "book.json")
        store.save(book, path)
        return store.load(path)


def status_events(book, invoice):
    return [e for e in book.audit.for_invoice(invoice.invoice_id) if e.kind == "invoice.status_changed"]


def refund_attrs(item):
    return (item.refund_id, item.invoice_id, item.quantities, item.net, item.tax, item.total,
            item.reason, item.actor, item.issued_on)


def audit_rows(book):
    return [(e.seq, e.kind, e.invoice_id, e.actor, e.at, e.data) for e in book.audit.events]


# 変更前の store.dump_book が書いた請求書 E の保存内容
OLD_FORMAT = {
    "schema_version": 1,
    "counters": {"invoice": 1, "payment": 1},
    "invoices": [
        {
            "invoice_id": "INV-0001",
            "customer_id": "C1",
            "currency": "JPY",
            "lines": [
                {"line_id": "L1", "sku": "A", "description": "商品A", "unit_price": "1000", "quantity": 3, "tax_rate": "0.10"},
                {"line_id": "L2", "sku": "B", "description": "商品B", "unit_price": "500", "quantity": 2, "tax_rate": "0.08"},
            ],
            "allowance": "0",
            "status": "paid",
            "issued_on": "2026-03-10",
            "due_on": "2026-03-31",
            "payments": [{"payment_id": "PAY-0001", "amount": "4380", "paid_on": "2026-03-20", "method": "bank_transfer"}],
            "memo": "",
        }
    ],
    "audit": [
        {"seq": 1, "kind": "invoice.status_changed", "invoice_id": "INV-0001", "actor": "alice", "at": "2026-03-10",
         "data": {"from": "draft", "to": "issued"}},
        {"seq": 2, "kind": "payment.recorded", "invoice_id": "INV-0001", "actor": "alice", "at": "2026-03-20",
         "data": {"payment_id": "PAY-0001", "amount": "4380", "method": "bank_transfer"}},
        {"seq": 3, "kind": "invoice.status_changed", "invoice_id": "INV-0001", "actor": "alice", "at": "2026-03-20",
         "data": {"from": "issued", "to": "paid"}},
    ],
}


class Trap1Persistence(unittest.TestCase):
    def test_refund_records_survive_save_and_load(self):  # AC-25 / 要件: 保存して読み直しても同じ
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 1})
        loaded = reload_book(book)
        self.assertEqual(
            [refund_attrs(r) for r in refund_list(loaded, invoice)],
            [refund_attrs(r) for r in refund_list(book, invoice)],
        )
        self.assertEqual(loaded.get_invoice(invoice.invoice_id).status, "partially_refunded")
        self.assertEqual(R.refundable_quantity(loaded, invoice.invoice_id, "L1"), 2)

    def test_audit_events_survive_save_and_load(self):  # AC-25
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 1})
        self.assertEqual(audit_rows(reload_book(book)), audit_rows(book))

    def test_refund_number_continues_after_load(self):  # AC-26 / 要件: 同じ番号を 2 度使わない
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 1})
        loaded = reload_book(book)
        second = refund(loaded, loaded.get_invoice(invoice.invoice_id), {"L1": 1})
        self.assertEqual(second.refund_id, "RF-0002")

    def test_cumulative_tax_continues_after_load(self):  # AC-27
        book = Book()
        invoice = invoice_a(book)
        refund(book, invoice, {"L1": 1})
        loaded = reload_book(book)
        second = refund(loaded, loaded.get_invoice(invoice.invoice_id), {"L1": 1})
        self.assertEqual(second.tax, D("98"))

    def test_tax_report_same_after_load(self):  # AC-27
        book = Book()
        invoice = invoice_a(book)
        refund(book, invoice, {"L1": 1})
        loaded = reload_book(book)
        self.assertEqual(tax_report(loaded, 2026, 4)["JPY"][RATE10], D("-97"))

    def test_old_format_file_loads_and_can_refund(self):  # AC-28 / plan: 変更前のコードが保存したファイルは読み込める
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "book.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(OLD_FORMAT, f, ensure_ascii=False)
            loaded = store.load(path)
        self.assertEqual(list(R.refunds_for(loaded, "INV-0001")), [])
        created = R.issue_refund(loaded, "INV-0001", {"L1": 1}, "返品", "alice", ON)
        self.assertEqual(created.refund_id, "RF-0001")


class Trap2Cache(unittest.TestCase):
    def test_summary_is_fresh_after_refund(self):  # AC-29 / 要件: 返金の前に呼んでいても古い値を返さない
        book = Book()
        invoice = invoice_e(book)
        customer_summary(book, "C1")
        refund(book, invoice, {"L1": 1})
        self.assertEqual(customer_summary(book, "C1")["JPY"]["refunded"], D("1100"))

    def test_revenue_of_refund_month_is_fresh(self):  # AC-31
        book = Book()
        invoice = invoice_e(book)
        monthly_revenue(book, 2026, 4)
        refund(book, invoice, {"L1": 1})
        self.assertEqual(monthly_revenue(book, 2026, 4)["JPY"], D("-1000"))

    def test_tax_report_of_refund_month_is_fresh(self):  # AC-32
        book = Book()
        invoice = invoice_e(book)
        tax_report(book, 2026, 4)
        refund(book, invoice, {"L1": 1})
        self.assertEqual(tax_report(book, 2026, 4)["JPY"][RATE10], D("-100"))

    def test_same_month_refund_is_fresh(self):  # AC-35
        book = Book()
        invoice = invoice_e(book)
        monthly_revenue(book, 2026, 3)
        tax_report(book, 2026, 3)
        refund(book, invoice, {"L1": 1}, on=date(2026, 3, 20))
        self.assertEqual(monthly_revenue(book, 2026, 3)["JPY"], D("3000"))
        report = tax_report(book, 2026, 3)["JPY"]
        self.assertEqual(report[RATE10], D("200"))
        self.assertEqual(report[RATE8], D("80"))

    def test_second_refund_is_reflected(self):  # 要件: 集計は返金の直後から反映する (状態が変わらない 2 回目も)
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 1})
        customer_summary(book, "C1")
        monthly_revenue(book, 2026, 4)
        tax_report(book, 2026, 4)
        refund(book, invoice, {"L1": 1})
        self.assertEqual(customer_summary(book, "C1")["JPY"]["refunded"], D("2200"))
        self.assertEqual(monthly_revenue(book, 2026, 4)["JPY"], D("-2000"))
        self.assertEqual(tax_report(book, 2026, 4)["JPY"][RATE10], D("-200"))


class Trap3Rounding(unittest.TestCase):
    def test_refund_is_based_on_net_after_allowance(self):  # AC-1
        book = Book()
        created = refund(book, invoice_a(book), {"L1": 1})
        self.assertEqual((created.net, created.tax, created.total), (D("975"), D("97"), D("1072")))
        self.assertEqual(created.refund_id, "RF-0001")

    def test_split_refund_tax_is_cumulative(self):  # AC-2
        book = Book()
        invoice = invoice_a(book)
        created = [refund(book, invoice, {"L1": 1}) for _ in range(3)]
        self.assertEqual([r.tax for r in created], [D("97"), D("98"), D("97")])
        self.assertEqual([r.total for r in created], [D("1072"), D("1073"), D("1072")])

    def test_full_refund_equals_invoice_total(self):  # AC-3
        book = Book()
        created = refund(book, invoice_a(book), {"L1": 3, "L2": 2})
        self.assertEqual((created.net, created.tax, created.total), (D("3900"), D("370"), D("4270")))

    def test_any_split_sums_to_invoice_total(self):  # AC-3 / 要件: どう分割しても全数量を返金した時点で累計は請求額に一致する
        book = Book()
        invoice = invoice_a(book)
        created = [refund(book, invoice, q) for q in ({"L1": 1, "L2": 1}, {"L1": 2}, {"L2": 1})]
        self.assertEqual(sum(r.net for r in created), D("3900"))
        self.assertEqual(sum(r.tax for r in created), D("370"))
        self.assertEqual(sum(r.total for r in created), D("4270"))

    def test_split_refund_of_other_rate(self):  # AC-4
        book = Book()
        invoice = invoice_a(book)
        created = [refund(book, invoice, {"L2": 1}) for _ in range(2)]
        self.assertEqual([r.net for r in created], [D("488"), D("487")])
        self.assertEqual([r.tax for r in created], [D("39"), D("39")])
        self.assertEqual([r.total for r in created], [D("527"), D("526")])

    def test_exact_half_rounds_up(self):  # AC-5
        book = Book()
        invoice = invoice_b(book)
        created = [refund(book, invoice, {"L1": 1}) for _ in range(2)]
        self.assertEqual([r.net for r in created], [D("13"), D("12")])
        self.assertEqual([r.tax for r in created], [D("1"), D("1")])
        self.assertEqual([r.total for r in created], [D("14"), D("13")])

    def test_tax_is_per_rate_not_per_line(self):  # AC-6
        book = Book()
        invoice = invoice_c(book)
        created = [refund(book, invoice, {"L1": 1}), refund(book, invoice, {"L2": 1})]
        self.assertEqual([r.tax for r in created], [D("1"), D("2")])
        self.assertEqual([r.total for r in created], [D("16"), D("17")])

    def test_usd_keeps_cents(self):  # AC-7
        book = Book()
        invoice = invoice_d(book)
        created = [refund(book, invoice, {"L1": 1}) for _ in range(2)]
        self.assertEqual([r.net for r in created], [D("10.01"), D("10.00")])
        self.assertEqual([r.tax for r in created], [D("1.00"), D("1.00")])
        self.assertEqual([r.total for r in created], [D("11.01"), D("11.00")])

    def test_same_rate_lines_round_per_line(self):  # 要件: 累計返金純額は明細ごとに四捨五入する
        book = Book()
        invoice = paid_invoice(book, [("25", 2, "0.10"), ("25", 2, "0.10")], allowance="2")
        item = refund(book, invoice, {"L1": 1, "L2": 1})
        self.assertEqual((item.net, item.tax), (D("50"), D("5")))

    def test_tax_report_keeps_cumulative_tax_across_months(self):  # 要件: 1 回の税額は累計の差で、返金日の月から差し引く
        book = Book()
        invoice = invoice_a(book)
        refund(book, invoice, {"L1": 1}, on=date(2026, 4, 15))
        refund(book, invoice, {"L1": 1}, on=date(2026, 5, 15))
        self.assertEqual(tax_report(book, 2026, 4)["JPY"][RATE10], D("-97"))
        self.assertEqual(tax_report(book, 2026, 5)["JPY"][RATE10], D("-98"))


class Trap4CallerInput(unittest.TestCase):
    def test_caller_quantities_are_not_modified(self):  # AC-17 / 要件: 渡した quantities を変更しない
        book = Book()
        quantities = {"L1": 1, "L2": 0}
        refund(book, invoice_e(book), quantities)
        self.assertEqual(quantities, {"L1": 1, "L2": 0})


class Trap5Audit(unittest.TestCase):
    def test_first_partial_refund_records_status_change(self):  # AC-20
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 1})
        self.assertEqual(invoice.status, "partially_refunded")
        self.assertEqual(status_events(book, invoice)[-1].data, {"from": "paid", "to": "partially_refunded"})

    def test_second_partial_refund_has_no_status_event(self):  # AC-21
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 1})
        before = len(status_events(book, invoice))
        refund(book, invoice, {"L1": 1})
        self.assertEqual(invoice.status, "partially_refunded")
        self.assertEqual(len(status_events(book, invoice)), before)
        self.assertEqual(len(book.audit.of_kind("refund.issued")), 2)

    def test_last_refund_moves_to_refunded(self):  # AC-22
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 1})
        refund(book, invoice, {"L1": 2, "L2": 2})
        self.assertEqual(invoice.status, "refunded")
        self.assertEqual(status_events(book, invoice)[-1].data, {"from": "partially_refunded", "to": "refunded"})

    def test_full_refund_at_once_moves_to_refunded(self):  # AC-23
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 3, "L2": 2})
        self.assertEqual(invoice.status, "refunded")
        self.assertEqual(status_events(book, invoice)[-1].data, {"from": "paid", "to": "refunded"})

    def test_refund_event_comes_before_status_event(self):  # AC-24
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 1})
        kinds = [e.kind for e in book.audit.for_invoice(invoice.invoice_id)]
        self.assertEqual(kinds[-2:], ["refund.issued", "invoice.status_changed"])

    def test_refund_event_fields(self):  # AC-24
        book = Book()
        invoice = invoice_e(book)
        created = refund(book, invoice, {"L1": 1}, reason="返品", actor="alice")
        event = book.audit.of_kind("refund.issued")[-1]
        self.assertEqual(event.invoice_id, invoice.invoice_id)
        self.assertEqual(event.actor, "alice")
        self.assertEqual(event.at, "2026-04-15")
        self.assertEqual(event.data["refund_id"], created.refund_id)
        self.assertEqual(event.data["reason"], "返品")

    def test_refund_event_amount_uses_same_form_as_payment(self):  # AC-24
        book = Book()
        refund(book, invoice_e(book), {"L1": 1})
        self.assertEqual(book.audit.of_kind("refund.issued")[-1].data["amount"], "1100")
        usd_book = Book()
        invoice = invoice_d(usd_book)
        refund(usd_book, invoice, {"L1": 1})
        self.assertEqual(usd_book.audit.of_kind("refund.issued")[-1].data["amount"], "11.01")
        refund(usd_book, invoice, {"L1": 1})
        self.assertEqual(usd_book.audit.of_kind("refund.issued")[-1].data["amount"], "11.00")


class Trap6UnawareCode(unittest.TestCase):
    def test_summary_keeps_counting_refunded_invoice(self):  # AC-29
        book = Book()
        refund(book, invoice_e(book), {"L1": 1})
        row = customer_summary(book, "C1")["JPY"]
        self.assertEqual(row["refunded"], D("1100"))
        self.assertEqual(row["billed"], D("4380"))
        self.assertEqual(row["paid"], D("4380"))
        self.assertEqual(row["outstanding"], D("0"))
        self.assertEqual(row["invoice_count"], 1)

    def test_summary_of_fully_refunded_invoice(self):  # 要件: billed などは返金の前後で変わらない (AC-29)
        book = Book()
        refund(book, invoice_e(book), {"L1": 3, "L2": 2})
        row = customer_summary(book, "C1")["JPY"]
        self.assertEqual(row["refunded"], D("4380"))
        self.assertEqual(row["billed"], D("4380"))
        self.assertEqual(row["invoice_count"], 1)

    def test_summary_without_refund_has_zero(self):  # AC-30
        book = Book()
        invoice_e(book)
        self.assertEqual(customer_summary(book, "C1")["JPY"]["refunded"], D("0"))

    def test_revenue_of_issue_month_is_kept(self):  # AC-31 / 要件: 発行月の集計に計上されたまま
        book = Book()
        refund(book, invoice_e(book), {"L1": 1})
        self.assertEqual(monthly_revenue(book, 2026, 3)["JPY"], D("4000"))

    def test_revenue_of_refund_month_is_reduced(self):  # AC-31
        book = Book()
        refund(book, invoice_e(book), {"L1": 1})
        self.assertEqual(monthly_revenue(book, 2026, 4)["JPY"], D("-1000"))

    def test_tax_of_issue_month_is_kept(self):  # AC-32
        book = Book()
        refund(book, invoice_e(book), {"L1": 1})
        report = tax_report(book, 2026, 3)["JPY"]
        self.assertEqual(report[RATE10], D("300"))
        self.assertEqual(report[RATE8], D("80"))

    def test_tax_of_refund_month_is_reduced_per_rate(self):  # AC-32
        book = Book()
        refund(book, invoice_e(book), {"L1": 1})
        report = tax_report(book, 2026, 4)["JPY"]
        self.assertEqual(report[RATE10], D("-100"))
        self.assertEqual(report.get(RATE8, D("0")), D("0"))

    def test_partially_refunded_is_not_overdue(self):  # AC-33
        book = Book()
        refund(book, invoice_e(book), {"L1": 1})
        self.assertEqual(overdue_invoices(book, date(2026, 4, 20)), [])

    def test_fully_refunded_is_not_overdue(self):  # AC-33
        book = Book()
        refund(book, invoice_e(book), {"L1": 3, "L2": 2})
        self.assertEqual(overdue_invoices(book, date(2026, 4, 20)), [])

    def test_duplicate_starts_without_refunds(self):  # AC-34
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 1})
        copy = duplicate_invoice(book, invoice.invoice_id)
        self.assertEqual(refund_list(book, copy), [])
        self.assertEqual(R.refundable_quantity(book, copy.invoice_id, "L1"), 3)
        self.assertEqual(R.refundable_quantity(book, copy.invoice_id, "L2"), 2)

    def test_duplicate_is_not_affected_by_later_refund_of_source(self):  # AC-34
        book = Book()
        invoice = invoice_e(book)
        copy = duplicate_invoice(book, invoice.invoice_id)
        refund(book, invoice, {"L1": 1})
        self.assertEqual(refund_list(book, copy), [])
        self.assertEqual(R.refundable_quantity(book, copy.invoice_id, "L1"), 3)

    def test_duplicate_of_refunded_invoice_can_be_fully_refunded(self):  # AC-34
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 3, "L2": 2})
        copy = duplicate_invoice(book, invoice.invoice_id)
        issue_invoice(book, copy.invoice_id, "alice", ISSUED_ON, DUE_ON)
        record_payment(book, copy.invoice_id, totals(copy).total, "bank_transfer", "alice", PAID_ON)
        created = refund(book, copy, {"L1": 3, "L2": 2})
        self.assertEqual(created.total, D("4380"))

    def test_full_refund_stays_in_reports(self):  # 要件: 請求書は返金のあとも発行月に計上し、返金は返金日の月から差し引く
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 3, "L2": 2})
        self.assertEqual(monthly_revenue(book, 2026, 3), {"JPY": D("4000")})
        self.assertEqual(tax_report(book, 2026, 3), {"JPY": {RATE10: D("300"), RATE8: D("80")}})
        self.assertEqual(monthly_revenue(book, 2026, 4), {"JPY": D("-4000")})
        self.assertEqual(tax_report(book, 2026, 4), {"JPY": {RATE10: D("-300"), RATE8: D("-80")}})


class Basics(unittest.TestCase):
    def test_refund_attributes_and_lookup(self):  # AC-8
        book = Book()
        invoice = invoice_e(book)
        created = refund(book, invoice, {"L1": 1}, reason="破損", actor="bob")
        self.assertEqual(len(refund_list(book, invoice)), 1)
        self.assertEqual(R.refundable_quantity(book, invoice.invoice_id, "L1"), 2)
        self.assertEqual(R.refundable_quantity(book, invoice.invoice_id, "L2"), 2)
        self.assertEqual(created.invoice_id, invoice.invoice_id)
        self.assertEqual(created.quantities, {"L1": 1})
        self.assertEqual(created.reason, "破損")
        self.assertEqual(created.actor, "bob")
        self.assertEqual(created.issued_on, ON)

    def test_unpaid_invoice_is_rejected(self):  # AC-9
        book = Book()
        invoice = create_invoice(book, "C1", "JPY")
        add_line(book, invoice.invoice_id, "SKU", "商品", "1000", 1, "0.10")
        issue_invoice(book, invoice.invoice_id, "alice", ISSUED_ON, DUE_ON)
        with self.assertRaises(InvalidTransition):
            refund(book, invoice, {"L1": 1})

    def test_fully_refunded_invoice_is_rejected(self):  # AC-10
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 3, "L2": 2})
        with self.assertRaises(InvalidTransition):
            refund(book, invoice, {"L1": 1})

    def test_quantity_over_invoiced(self):  # AC-11
        book = Book()
        with self.assertRaises(ValidationError):
            refund(book, invoice_e(book), {"L1": 4})

    def test_quantity_over_remaining(self):  # AC-12
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 2})
        with self.assertRaises(ValidationError):
            refund(book, invoice, {"L1": 2})

    def test_fractional_quantity(self):  # AC-13
        book = Book()
        with self.assertRaises(ValidationError):
            refund(book, invoice_e(book), {"L1": 1.5})

    def test_negative_quantity(self):  # AC-14
        book = Book()
        with self.assertRaises(ValidationError):
            refund(book, invoice_e(book), {"L1": -1})

    def test_nothing_to_refund(self):  # AC-15
        book = Book()
        invoice = invoice_e(book)
        with self.assertRaises(ValidationError):
            refund(book, invoice, {})
        with self.assertRaises(ValidationError):
            refund(book, invoice, {"L1": 0})

    def test_unknown_line_and_invoice(self):  # AC-16
        book = Book()
        invoice = invoice_e(book)
        with self.assertRaises(NotFound):
            refund(book, invoice, {"L9": 1})
        with self.assertRaises(NotFound):
            R.issue_refund(book, "INV-9999", {"L1": 1}, "返品", "alice", ON)

    def test_zero_row_is_ignored(self):  # AC-17
        book = Book()
        invoice = invoice_e(book)
        created = refund(book, invoice, {"L1": 1, "L2": 0})
        self.assertEqual(created.quantities, {"L1": 1})
        self.assertEqual(R.refundable_quantity(book, invoice.invoice_id, "L2"), 2)

    def test_failed_call_leaves_nothing(self):  # AC-18
        book = Book()
        invoice = invoice_e(book)
        events_before = audit_rows(book)
        with self.assertRaises(ValidationError):
            refund(book, invoice, {"L1": 1, "L2": 99})
        self.assertEqual(refund_list(book, invoice), [])
        self.assertEqual(invoice.status, "paid")
        self.assertEqual(audit_rows(book), events_before)
        self.assertEqual(refund(book, invoice, {"L1": 1}).refund_id, "RF-0001")

    def test_invoice_lines_and_total_are_unchanged(self):  # AC-19
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 2})
        self.assertEqual([line.quantity for line in invoice.lines], [3, 2])
        self.assertEqual(totals(invoice).total, D("4380"))

    def test_unpaid_rejection_leaves_nothing(self):  # 要件: 例外を送出した呼び出しは何も残さない
        book = Book()
        invoice = create_invoice(book, "C1", "JPY")
        add_line(book, invoice.invoice_id, "SKU", "商品", "1000", 1, "0.10")
        issue_invoice(book, invoice.invoice_id, "alice", ISSUED_ON, DUE_ON)
        before = audit_rows(book)
        with self.assertRaises(InvalidTransition):
            refund(book, invoice, {"L1": 1})
        self.assertEqual(refund_list(book, invoice), [])
        self.assertEqual(audit_rows(book), before)
        self.assertEqual(refund(book, invoice_e(book), {"L1": 1}).refund_id, "RF-0001")

    def test_only_paid_invoices_can_be_refunded(self):  # 要件: 返金できるのは paid か partially_refunded だけ
        book = Book()
        invoice = create_invoice(book, "C1", "JPY")
        add_line(book, invoice.invoice_id, "SKU", "商品", "1000", 2, "0.10")
        with self.assertRaises(InvalidTransition):
            refund(book, invoice, {"L1": 1})  # draft
        issue_invoice(book, invoice.invoice_id, "alice", ISSUED_ON, DUE_ON)
        record_payment(book, invoice.invoice_id, "100", "cash", "alice", PAID_ON)
        with self.assertRaises(InvalidTransition):
            refund(book, invoice, {"L1": 1})  # partially_paid
        self.assertEqual(invoice.status, "partially_paid")
        self.assertEqual(refund_list(book, invoice), [])


class SpecBeyondTable(unittest.TestCase):
    def test_refund_numbers_run_across_the_book(self):  # 要件: 返金番号は帳簿全体の連番
        book = Book()
        first, second = invoice_e(book), invoice_e(book)
        ids = [refund(book, first, {"L1": 1}).refund_id, refund(book, second, {"L1": 1}).refund_id]
        self.assertEqual(ids, ["RF-0001", "RF-0002"])

    def test_refunds_for_is_oldest_first(self):  # 要件: refunds_for は古い順に返す
        book = Book()
        invoice = invoice_e(book)
        created = [refund(book, invoice, {"L1": 1}).refund_id, refund(book, invoice, {"L2": 1}).refund_id]
        self.assertEqual([r.refund_id for r in refund_list(book, invoice)], created)

    def test_tax_report_splits_one_refund_by_rate(self):  # 要件: tax_report は返金の税額を税率ごとに差し引く
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 1, "L2": 1})
        self.assertEqual(tax_report(book, 2026, 4), {"JPY": {RATE10: D("-100"), RATE8: D("-40")}})

    def test_tax_report_uses_each_refunds_tax(self):  # 要件: 1 回の税額は累計の差で、tax_report はその税額を差し引く
        book = Book()
        invoice = invoice_a(book)
        for _ in range(3):
            refund(book, invoice, {"L1": 1})
        self.assertEqual(tax_report(book, 2026, 4)["JPY"][RATE10], D("-292"))

    def test_summary_refunded_sums_every_refund(self):  # 要件: refunded はその通貨の返金の total の合計
        book = Book()
        invoice = invoice_e(book)
        totals_of = [refund(book, invoice, {"L1": 1}).total, refund(book, invoice, {"L1": 1}).total]
        self.assertEqual(customer_summary(book, "C1")["JPY"]["refunded"], sum(totals_of))

    def test_out_of_scope_reports_are_unchanged(self):  # spec のスコープ外: customer_statement と taxable_base_report
        book = Book()
        invoice = invoice_e(book)
        before = customer_statement(book, "C1")[0]
        refund(book, invoice, {"L1": 1})
        after = customer_statement(book, "C1")[0]
        self.assertEqual((after["total"], after["paid"]), (before["total"], before["paid"]))
        self.assertEqual(taxable_base_report(book, 2026, 4), {})
        self.assertEqual(taxable_base_report(book, 2026, 3), {"JPY": {RATE10: D("3000"), RATE8: D("1000")}})

    def test_refunds_stay_in_their_currency(self):  # 要件: refunded はその通貨の返金の total の合計
        book = Book()
        refund(book, invoice_e(book), {"L1": 1})
        refund(book, invoice_d(book), {"L1": 1})
        summary = customer_summary(book, "C1")
        self.assertEqual((summary["JPY"]["refunded"], summary["USD"]["refunded"]), (D("1100"), D("11.01")))
        self.assertEqual(monthly_revenue(book, 2026, 4), {"JPY": D("-1000"), "USD": D("-10.01")})


class Preserved(unittest.TestCase):
    def test_version_kept(self):  # plan: billing.__version__ は変えない
        self.assertEqual(billing.__version__, "0.4.0")

    def test_values_without_refund_are_kept(self):  # plan: 返金のない請求書の集計の値は変えない
        book = Book()
        invoice = invoice_e(book)
        row = customer_summary(book, "C1")["JPY"]
        self.assertEqual((row["billed"], row["paid"], row["outstanding"], row["invoice_count"]),
                         (D("4380"), D("4380"), D("0"), 1))
        self.assertEqual(monthly_revenue(book, 2026, 3), {"JPY": D("4000")})
        self.assertEqual(tax_report(book, 2026, 3), {"JPY": {RATE10: D("300"), RATE8: D("80")}})
        self.assertEqual(overdue_invoices(book, date(2026, 4, 20)), [])
        self.assertEqual(invoice.status, "paid")

    def test_old_format_data_loads(self):  # plan: 変更前のコードが保存したファイルは読み込める
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "book.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(OLD_FORMAT, f, ensure_ascii=False)
            loaded = store.load(path)
        self.assertEqual(totals(loaded.get_invoice("INV-0001")).total, D("4380"))
        self.assertEqual(len(loaded.audit.events), 3)

    def test_refunded_invoice_rejects_payment(self):  # plan: 返金が記録された請求書には入金できない
        book = Book()
        invoice = invoice_e(book)
        refund(book, invoice, {"L1": 1})
        with self.assertRaises(InvalidTransition):
            record_payment(book, invoice.invoice_id, "100", "cash", "alice", ON)


if __name__ == "__main__":
    unittest.main()
