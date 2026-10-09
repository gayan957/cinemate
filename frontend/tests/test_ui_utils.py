"""Run from repository root with: python -m unittest discover -s frontend/tests"""

import unittest

from frontend.ui_utils import api_error_message, label_for_media, poster_for, useful_recommendations


class UiUtilsTests(unittest.TestCase):
    def test_tv_label(self):
        self.assertEqual(label_for_media("tv"), "TV series")
        self.assertEqual(label_for_media("movie"), "Movie")

    def test_filters_bad_records(self):
        self.assertEqual(useful_recommendations({"recommendations": [{"title": "Arrival"}, {}, None]}), [{"title": "Arrival"}])

    def test_handles_no_recommendations(self):
        self.assertEqual(useful_recommendations({}), [])

    def test_matches_poster_by_title_and_year(self):
        posters = [{"title": "Lost", "year": 2004, "poster_url": "https://example.com/lost.jpg"}]
        self.assertEqual(poster_for({"title": "lost", "year": 2004}, posters), "https://example.com/lost.jpg")

    def test_does_not_use_wrong_poster(self):
        self.assertIsNone(poster_for({"title": "Lost", "year": 2010}, [{"title": "Lost", "year": 2004, "poster_url": "url"}]))

    def test_rate_limit_error(self):
        self.assertIn("daily", api_error_message(429).lower())

    def test_timeout_error(self):
        self.assertIn("longer", api_error_message(503))


if __name__ == "__main__":
    unittest.main()
