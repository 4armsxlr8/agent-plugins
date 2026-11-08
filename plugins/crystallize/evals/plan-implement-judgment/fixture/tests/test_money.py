import unittest
from decimal import Decimal

from shipping.money import round_yen


class RoundYen(unittest.TestCase):
    def test_truncates(self):
        self.assertEqual(round_yen(Decimal("61.5")), 61)
        self.assertEqual(round_yen(Decimal("61.9")), 61)
        self.assertEqual(round_yen(Decimal("61")), 61)
