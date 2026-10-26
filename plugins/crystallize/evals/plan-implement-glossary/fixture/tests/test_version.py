import unittest

import tasks


class VersionTest(unittest.TestCase):
    def test_version_is_string(self):
        self.assertIsInstance(tasks.__version__, str)


if __name__ == "__main__":
    unittest.main()
