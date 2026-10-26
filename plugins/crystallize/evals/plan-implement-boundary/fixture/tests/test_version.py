import unittest

import workdays


class VersionTest(unittest.TestCase):
    def test_version_is_string(self):
        self.assertIsInstance(workdays.__version__, str)


if __name__ == "__main__":
    unittest.main()
