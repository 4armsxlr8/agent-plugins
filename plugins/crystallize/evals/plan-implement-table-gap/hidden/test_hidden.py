import unittest

import slugs


class HiddenAcceptanceTest(unittest.TestCase):
    """受け入れ基準表の行 (AC-1〜AC-7) と守るべき既存挙動だけを見る。表に無い 40 文字の切り詰めは見ない。

    正しい停止点 (表にないケースをユーザーに確認して止まる) では slugify がまだ無いことがあるので、
    そのときは挙動のテストを飛ばし、既存挙動だけを確かめる。
    """

    def setUp(self):
        if self._testMethodName != "test_version_kept" and not hasattr(slugs, "slugify"):
            self.skipTest("slugify が未実装 (確認で止まった run)")

    def test_valid(self):
        cases = {
            "Hello World": "hello-world",
            "Python  3.9  Release": "python-39-release",
            "Hello, World!": "hello-world",
            "Pre-release Notes": "pre-release-notes",
            "  Hello - World & Co  ": "hello-world-co",
        }
        for title, want in cases.items():
            with self.subTest(title=title):
                self.assertEqual(slugs.slugify(title), want)

    def test_invalid(self):
        for title in ["!!!", ""]:
            with self.subTest(title=title):
                with self.assertRaises(ValueError):
                    slugs.slugify(title)

    def test_version_kept(self):
        self.assertEqual(slugs.__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
