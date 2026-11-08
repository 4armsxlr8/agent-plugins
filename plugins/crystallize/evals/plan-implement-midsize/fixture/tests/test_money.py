import unittest
from decimal import Decimal as D

from billing.errors import ValidationError
from billing.money import allocate, format_amount, is_payable_amount, round_money, truncate_money, zero


class RoundingTest(unittest.TestCase):
    def test_round_money_is_half_up(self):
        self.assertEqual(round_money(D("12.5"), "JPY"), D("13"))
        self.assertEqual(round_money(D("10.005"), "USD"), D("10.01"))

    def test_truncate_money(self):
        self.assertEqual(truncate_money(D("9.9"), "JPY"), D("9"))
        self.assertEqual(truncate_money(D("1.999"), "USD"), D("1.99"))

    def test_unknown_currency(self):
        with self.assertRaises(ValidationError):
            round_money(D("1"), "XXX")

    def test_format_amount(self):
        self.assertEqual(format_amount(D("1072"), "JPY"), "1072")
        self.assertEqual(format_amount(D("5.5"), "USD"), "5.50")
        self.assertEqual(format_amount(zero("USD"), "USD"), "0.00")

    def test_is_payable_amount(self):
        self.assertTrue(is_payable_amount(D("1.25"), "USD"))
        self.assertFalse(is_payable_amount(D("1.25"), "JPY"))
        self.assertFalse(is_payable_amount(D("0"), "JPY"))


class AllocateTest(unittest.TestCase):
    def test_parts_sum_to_total(self):
        parts = allocate(D("100"), [D("1"), D("1"), D("1")], "JPY")
        self.assertEqual(sum(parts), D("100"))
        self.assertEqual(parts, [D("34"), D("33"), D("33")])

    def test_proportional(self):
        self.assertEqual(allocate(D("100"), [D("3000"), D("1000")], "JPY"), [D("75"), D("25")])

    def test_largest_fraction_gets_remainder(self):
        self.assertEqual(allocate(D("10"), [D("1"), D("2")], "JPY"), [D("3"), D("7")])

    def test_zero_weights(self):
        self.assertEqual(allocate(D("10"), [D("0"), D("0")], "JPY"), [D("0"), D("0")])


if __name__ == "__main__":
    unittest.main()
