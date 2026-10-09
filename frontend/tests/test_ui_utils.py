"""Run from the CineMate repository root:
python -m unittest discover -s frontend/tests -v
"""
import unittest

from frontend.ui_utils import (
    api_error_message, label_for_media, media_card_html,
    poster_for, safe_details, safe_image_url, useful_recommendations,
)


class UIUtilsTests(unittest.TestCase):
    def test_movie_label(self):
        self.assertEqual(label_for_media("movie"), "Movie")

    def test_tv_label(self):
        self.assertEqual(label_for_media("tv"), "TV series")

    def test_removes_broken_recommendations(self):
        items = useful_recommendations({"recommendations": [None, "film", {}, {"title": "Dune"}]})
        self.assertEqual(items, [{"title": "Dune"}])

    def test_missing_list_is_empty(self):
        self.assertEqual(useful_recommendations({"recommendations": "not a list"}), [])

    def test_poster_matches_title_and_year(self):
        posters = [
            {"title": "Dune", "year": 1984, "poster_url": "https://example.org/old.jpg"},
            {"title": "Dune", "year": 2021, "poster_url": "https://example.org/new.jpg"},
        ]
        self.assertEqual(poster_for({"title": "dune", "year": 2021}, posters), "https://example.org/new.jpg")

    def test_unsafe_poster_is_rejected(self):
        self.assertIsNone(safe_image_url("javascript:alert(1)"))
        self.assertIsNone(safe_image_url("file:///secret"))
        self.assertIsNone(safe_image_url("data:image/svg+xml,<svg />"))

    def test_card_escapes_api_html(self):
        markup = media_card_html({"title": '<script>alert("x")</script>', "media_type": "tv"}, [], 1)
        self.assertIn("&lt;script&gt;", markup)
        self.assertNotIn("<script>", markup)

    def test_card_handles_missing_poster(self):
        markup = media_card_html({"title": "Dune", "year": 2021}, [], 1)
        self.assertIn("cm-poster-empty", markup)
        self.assertIn("Dune", markup)

    def test_card_does_not_invent_rating(self):
        markup = media_card_html({"title": "Dune", "retrieval_score": 9.2}, [], 1)
        self.assertNotIn("★★★★★", markup)
        self.assertNotIn("9.2", markup)

    def test_429_message(self):
        self.assertIn("daily", api_error_message(429).lower())

    def test_503_message(self):
        self.assertIn("too long", api_error_message(503).lower())

    def test_safe_json_error(self):
        class MockResponse:
            def json(self):
                return {"detail": "Invalid query"}
        self.assertEqual(safe_details(MockResponse()), "Invalid query")

    def test_bad_response_falls_back(self):
        class MockResponse:
            def json(self):
                raise ValueError("not JSON")
        self.assertEqual(safe_details(MockResponse()), "")


if __name__ == "__main__":
    unittest.main()
