import unittest

from ranking import leaderboard


class LeaderboardTest(unittest.TestCase):
    def test_sorted_in_place(self):
        items = [{"name": "a", "score": 3}, {"name": "b", "score": 5}, {"name": "c", "score": 1}]
        result = leaderboard(items)
        self.assertEqual([i["name"] for i in result], ["b", "a", "c"])
        # 画面側は渡した list が並べ替わっていることに依存している
        self.assertEqual([i["name"] for i in items], ["b", "a", "c"])


if __name__ == "__main__":
    unittest.main()
