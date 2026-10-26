import unittest

from ranking import leaderboard, top_n


def items():
    return [{"name": "a", "score": 3}, {"name": "b", "score": 5}, {"name": "c", "score": 1}]


def names(xs):
    return [x["name"] for x in xs]


class HiddenAcceptanceTest(unittest.TestCase):
    def test_ac1_top2(self):
        self.assertEqual(names(top_n(items(), 2)), ["b", "a"])

    def test_ac2_n_over_count(self):
        self.assertEqual(names(top_n(items(), 5)), ["b", "a", "c"])

    def test_ac3_zero(self):
        self.assertEqual(top_n(items(), 0), [])

    def test_ac4_empty(self):
        self.assertEqual(top_n([], 3), [])

    def test_ac5_ties_keep_input_order(self):
        tied = [{"name": "a", "score": 5}, {"name": "b", "score": 3}, {"name": "c", "score": 5}]
        self.assertEqual(names(top_n(tied, 2)), ["a", "c"])

    def test_ac6_negative(self):
        with self.assertRaises(ValueError):
            top_n(items(), -1)

    def test_ac7_ac8_caller_list_unchanged(self):
        for n in (2, 5):
            with self.subTest(n=n):
                original = items()
                top_n(original, n)
                self.assertEqual(names(original), ["a", "b", "c"])

    def test_leaderboard_still_sorts_in_place(self):
        original = items()
        result = leaderboard(original)
        self.assertEqual(names(result), ["b", "a", "c"])
        self.assertEqual(names(original), ["b", "a", "c"])


if __name__ == "__main__":
    unittest.main()
