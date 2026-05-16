import unittest

from app.services.place_repository_service import _canonical_match, _token_query


class PlaceRepositoryServiceTests(unittest.TestCase):
    def test_canonical_match_supports_korean_aliases(self) -> None:
        self.assertEqual(_canonical_match("센강 산책")["name"], "Seine River")
        self.assertEqual(_canonical_match("루브르 박물관")["name"], "Louvre Museum")
        self.assertEqual(_canonical_match("오페라 가르니에")["name"], "Palais Garnier")

    def test_token_query_keeps_requested_category_for_landmarks(self) -> None:
        query = _token_query("센강 산책", "landmark")

        self.assertIsNotNone(query)
        self.assertEqual(query["category"], "landmark")


if __name__ == "__main__":
    unittest.main()
