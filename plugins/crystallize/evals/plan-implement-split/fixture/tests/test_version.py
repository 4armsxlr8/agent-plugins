import unittest

import wordcount


class VersionTest(unittest.TestCase):
    def test_version_is_string(self):
        self.assertIsInstance(wordcount.__version__, str)


if __name__ == "__main__":
    unittest.main()
