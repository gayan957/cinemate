"""Run from repository root with: python -m unittest discover -s frontend/tests"""

import unittest

from frontend.ui_utils import label_for_media


class UiUtilsTests(unittest.TestCase):
    def test_tv_label(self):
        self.assertEqual(label_for_media("tv"), "TV series")
        self.assertEqual(label_for_media("movie"), "Movie")


if __name__ == "__main__":
    unittest.main()
