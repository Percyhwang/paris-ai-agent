import unittest

from parser_api.services.place_catalog import _item_role, build_itinerary, resolve_place


class PlaceCatalogProfileGenerationTests(unittest.TestCase):
    def test_resolve_place_short_arc_query_prefers_arc_de_triomphe(self) -> None:
        resolved = resolve_place("arc")

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.get("slug"), "arc-de-triomphe")

    def test_landmark_role_is_not_downgraded_to_walking_route_by_walk_tags(self) -> None:
        role = _item_role(
            {"category": "landmark", "tags": ["landmark", "classic"]},
            slot="afternoon",
            slot_tags=["walk", "photo", "scenic"],
            is_meal=False,
        )

        self.assertEqual(role, "landmark")

    def test_cathedral_role_is_not_recast_as_shopping_by_slot_tags(self) -> None:
        role = _item_role(
            {"category": "cathedral", "tags": ["history", "architecture"]},
            slot="afternoon",
            slot_tags=["shopping", "local"],
            is_meal=False,
        )

        self.assertEqual(role, "landmark")

    def test_family_profile_avoids_nightlife_stops(self) -> None:
        trip = build_itinerary(
            {
                "dates": {"start_date": "2026-06-29", "days": 2},
                "preferences": {
                    "themes": ["family", "local"],
                    "travel_style": ["slow", "family", "local"],
                    "meal_preference": ["cafe", "french"],
                },
                "pace": {"level": "slow"},
                "mobility": {"travel_mode": "transit", "max_walk_km_per_day": 5},
                "party": {"adult": 2, "elementary": 1, "trip_style": "family"},
                "planning_brief": {
                    "travel_style": ["slow", "family", "local"],
                    "meal_preference": ["cafe", "french"],
                    "pace": "slow",
                    "source_text": "가족 여행이라 아이랑 많이 걷지 않고 조용하고 로컬하게",
                },
            }
        )

        categories = {
            str((item.get("place") or {}).get("category") or "")
            for day in trip["itinerary_days"]
            for item in day["items"]
        }
        roles = {
            str(item.get("role") or "")
            for day in trip["itinerary_days"]
            for item in day["items"]
        }

        self.assertTrue(categories.isdisjoint({"bar", "wine_bar"}))
        self.assertNotIn("night_activity", roles)

    def test_local_quiet_profile_prefers_local_support_stops(self) -> None:
        trip = build_itinerary(
            {
                "dates": {"start_date": "2026-06-29", "days": 2},
                "preferences": {
                    "themes": ["local"],
                    "travel_style": ["slow", "local"],
                    "meal_preference": ["cafe"],
                },
                "pace": {"level": "slow"},
                "planning_brief": {
                    "travel_style": ["slow", "local"],
                    "meal_preference": ["cafe"],
                    "pace": "slow",
                    "source_text": "로컬하고 조용하게 너무 관광지스럽지 않게",
                },
            }
        )

        for day in trip["itinerary_days"]:
            local_support_count = sum(
                1
                for item in day["items"]
                if str((item.get("place") or {}).get("category") or "") in {"neighborhood", "park", "cafe", "bakery"}
                or str(item.get("role") or "") in {"lunch", "dinner"}
            )
            tourist_heavy_count = sum(
                1
                for item in day["items"]
                if str((item.get("place") or {}).get("category") or "") in {"museum", "landmark", "cathedral", "shopping"}
            )
            self.assertGreaterEqual(local_support_count, 3)
            self.assertLessEqual(tourist_heavy_count, 1)

    def test_shopping_foodie_profile_surfaces_shopping_and_meal_concepts(self) -> None:
        trip = build_itinerary(
            {
                "dates": {"start_date": "2026-06-29", "days": 2},
                "preferences": {
                    "themes": ["shopping", "foodie"],
                    "travel_style": ["shopping", "foodie", "normal"],
                    "meal_preference": ["french", "dessert"],
                },
                "planning_brief": {
                    "travel_style": ["shopping", "foodie"],
                    "meal_preference": ["french", "dessert"],
                    "pace": "normal",
                    "source_text": "쇼핑이랑 맛집 위주로 가고 싶어",
                },
            }
        )

        roles = {
            str(item.get("role") or "")
            for day in trip["itinerary_days"]
            for item in day["items"]
        }
        meal_like_count = sum(
            1
            for day in trip["itinerary_days"]
            for item in day["items"]
            if str(item.get("role") or "") in {"lunch", "dinner", "cafe_break", "dessert"}
        )

        self.assertIn("shopping", roles)
        self.assertGreaterEqual(meal_like_count, 3)

    def test_museum_limit_per_day_caps_museum_density(self) -> None:
        trip = build_itinerary(
            {
                "dates": {"start_date": "2026-06-29", "days": 2},
                "preferences": {
                    "themes": ["art", "museum"],
                    "travel_style": ["museum", "art"],
                    "meal_preference": ["french"],
                },
                "pace": {"level": "normal"},
                "planning_brief": {
                    "travel_style": ["museum", "art"],
                    "meal_preference": ["french"],
                    "pace": "normal",
                    "museum_limit_per_day": 1,
                    "source_text": "미술관 여행인데 하루 미술관은 한 곳만",
                },
            }
        )

        for day in trip["itinerary_days"]:
            museum_count = sum(
                1
                for item in day["items"]
                if str((item.get("place") or {}).get("category") or "") == "museum"
            )
            self.assertLessEqual(museum_count, 1)

    def test_rainy_indoor_jazz_profile_keeps_indoor_main_activity_and_nightlife(self) -> None:
        trip = build_itinerary(
            {
                "dates": {"start_date": "2026-06-29", "days": 2},
                "preferences": {
                    "themes": ["museum", "art", "indoor", "nightlife"],
                    "travel_style": ["museum", "art", "indoor", "nightlife"],
                    "meal_preference": ["jazz_bar", "french"],
                },
                "planning_brief": {
                    "travel_style": ["museum", "art", "indoor", "nightlife"],
                    "meal_preference": ["jazz_bar", "french"],
                    "pace": "normal",
                    "source_text": "비 오는 날에도 괜찮게 실내 위주로 짜고 저녁에는 재즈바 같은 분위기도 있었으면 해.",
                },
            }
        )

        night_roles = {
            str(item.get("role") or "")
            for day in trip["itinerary_days"]
            for item in day["items"]
        }
        cafe_break_count = sum(
            1
            for day in trip["itinerary_days"]
            for item in day["items"]
            if str(item.get("role") or "") == "cafe_break"
        )
        dinner_count = sum(
            1
            for day in trip["itinerary_days"]
            for item in day["items"]
            if str(item.get("role") or "") == "dinner"
        )
        for day in trip["itinerary_days"]:
            indoor_main_count = sum(
                1
                for item in day["items"]
                if str(item.get("role") or "") in {"museum_or_gallery", "landmark", "main_activity"}
                and str((item.get("place") or {}).get("category") or "") in {"museum", "gallery", "cathedral", "landmark"}
            )
            self.assertGreaterEqual(indoor_main_count, 1)

        self.assertGreaterEqual(cafe_break_count, 1)
        self.assertGreaterEqual(dinner_count, 1)
        self.assertIn("night_activity", night_roles)


if __name__ == "__main__":
    unittest.main()
