"""Run from repository root with: python -m unittest discover -s frontend/tests"""

import unittest

from frontend.ui_utils import label_for_media, useful_recommendations


class UiUtilsTests(unittest.TestCase):
    def test_tv_label(self):
        self.assertEqual(label_for_media("tv"), "TV series")
        self.assertEqual(label_for_media("movie"), "Movie")

    def test_filters_bad_records(self):
        self.assertEqual(useful_recommendations({"recommendations": [{"title": "Arrival"}, {}, None]}), [{"title": "Arrival"}])

    def test_handles_no_recommendations(self):
        self.assertEqual(useful_recommendations({}), [])


if __name__ == "__main__":
    unittest.main()
