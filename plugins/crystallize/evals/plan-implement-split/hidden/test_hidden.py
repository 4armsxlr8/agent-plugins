import unittest

from wordcount import count_words


class HiddenAcceptanceTest(unittest.TestCase):
    """1 枚目の plan の covers (AC-1, AC-2, AC-3) だけを見る"""

    def test_count_words(self):
        cases = {"hello world": 2, "": 0, "  a\n\tb   c ": 3}  # AC-1, AC-2, AC-3
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(count_words(text), want)
                self.assertIsInstance(count_words(text), int)

    def test_version_kept(self):
        import wordcount
        self.assertEqual(wordcount.__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
