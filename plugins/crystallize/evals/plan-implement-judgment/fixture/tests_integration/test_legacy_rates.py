import unittest

from shipping.rates import load_legacy_rates


class LegacyRates(unittest.TestCase):
    def test_distributed_table(self):
        # data/rates_2025.csv は経理が配布するファイルで、リポジトリには置かない
        rates = load_legacy_rates("data/rates_2025.csv")
        self.assertEqual(rates["tokyo"], 600)
