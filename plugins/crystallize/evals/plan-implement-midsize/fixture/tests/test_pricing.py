import unittest
from decimal import Decimal as D

from billing.book import Book
from billing.invoices import add_line, create_invoice, set_allowance
from billing.pricing import line_nets, tax_on, taxes_by_rate, totals


def invoice_with(lines, allowance="0", currency="JPY"):
    book = Book()
    invoice = create_invoice(book, "C1", currency)
    for sku, price, qty, rate in lines:
        add_line(book, invoice.invoice_id, sku, sku, price, qty, rate)
    set_allowance(book, invoice.invoice_id, allowance)
    return invoice


class PricingTest(unittest.TestCase):
    def test_line_nets_share_allowance_by_subtotal(self):
        invoice = invoice_with([("A", "1000", 3, "0.10"), ("B", "500", 2, "0.08")], allowance="100")
        self.assertEqual(dict(line_nets(invoice)), {"L1": D("2925"), "L2": D("975")})

    def test_tax_is_truncated_per_rate(self):
        invoice = invoice_with([("A", "1000", 3, "0.10"), ("B", "500", 2, "0.08")], allowance="100")
        self.assertEqual(dict(taxes_by_rate(invoice)), {D("0.10"): D("292"), D("0.08"): D("78")})

    def test_same_rate_lines_are_summed_before_truncation(self):
        invoice = invoice_with([("A", "15", 1, "0.10"), ("B", "15", 1, "0.10")])
        self.assertEqual(totals(invoice).tax, D("3"))

    def test_totals(self):
        invoice = invoice_with([("A", "1000", 3, "0.10"), ("B", "500", 2, "0.08")], allowance="100")
        result = totals(invoice)
        self.assertEqual(result.subtotal, D("4000"))
        self.assertEqual(result.net, D("3900"))
        self.assertEqual(result.tax, D("370"))
        self.assertEqual(result.total, D("4270"))

    def test_usd_tax_keeps_cents(self):
        invoice = invoice_with([("A", "19.99", 3, "0.10")], currency="USD")
        self.assertEqual(totals(invoice).tax, D("5.99"))
        self.assertEqual(tax_on(D("19.99"), D("0.10"), "USD"), D("1.99"))


if __name__ == "__main__":
    unittest.main()
