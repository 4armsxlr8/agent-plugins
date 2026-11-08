import unittest

from shipping.export import export_row
from shipping.fees import quote
from shipping.orders import Parcel


class Quote(unittest.TestCase):
    def test_paid_shipping(self):
        result = quote(Parcel(1000, "tokyo", 3000))
        self.assertEqual(result, {"breakdown": {"base": 615, "remote": 0, "tax": 61}, "total": 676})

    def test_free_shipping(self):
        self.assertEqual(quote(Parcel(1000, "tokyo", 20000))["total"], 0)

    def test_remote(self):
        self.assertEqual(quote(Parcel(1000, "hokkaido", 3000))["breakdown"]["remote"], 400)

    def test_too_heavy(self):
        with self.assertRaises(ValueError):
            quote(Parcel(20001, "tokyo", 3000))


class Export(unittest.TestCase):
    def test_row(self):
        self.assertEqual(export_row("A1", Parcel(1000, "tokyo", 3000)), "A1,615,0,61,676")
