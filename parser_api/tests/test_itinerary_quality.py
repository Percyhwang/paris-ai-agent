import unittest

from parser_api.parsers.create_plan.parser import parse_create_plan
from parser_api.services.place_catalog import build_itinerary


class CreatePlanPreferenceExtractionTests(unittest.TestCase):
    def test_rule_parser_extracts_story_relevant_preferences(self) -> None:
        payload = parse_create_plan(
            "파리 4일 일정 짜줘. 야경 위주로 천천히 다니고 브런치 카페 좋아해. 오후부터 시작해서 저녁 위주로."
        ).model_dump()

        preferences = payload["preferences"]

        self.assertTrue(preferences["night_view_required"])
        self.assertIn("night_view", preferences["themes"])
        self.assertIn("slow", preferences["travel_style"])
        self.assertIn("afternoon", preferences["preferred_time_slots"])
        self.assertIn("evening", preferences["preferred_time_slots"])
        self.assertIn("brunch", preferences["meal_preference"])
        self.assertIn("cafe", preferences["meal_preference"])
        self.assertEqual(payload["pace"]["level"], "slow")


class PlaceCatalogItineraryQualityTests(unittest.TestCase):
    def test_brunch_rainy_jazz_profile_caps_cafe_density(self) -> None:
        trip = build_itinerary(
            {
                "dates": {"start_date": "2026-06-29", "days": 3},
                "preferences": {
                    "themes": ["indoor", "night_view"],
                    "travel_style": ["slow", "indoor"],
                    "meal_preference": ["brunch", "jazz"],
                    "night_view_required": True,
                },
                "pace": {"level": "slow"},
                "planning_brief": {
                    "source_text": "비 오는 날이라 실내 위주로 보고 싶고 브런치는 좋지만 카페를 여러 번 넣고 싶진 않아. 재즈는 한 번만.",
                    "travel_style": ["slow", "indoor", "night_view"],
                    "meal_preference": ["brunch", "jazz"],
                    "night_view_required": True,
                    "pace": "slow",
                    "strict_constraints": True,
                },
            }
        )

        for day in trip["itinerary_days"]:
            cafe_like = [
                item
                for item in day["items"]
                if (item.get("place") or {}).get("category") in {"cafe", "bakery"}
            ]
            self.assertLessEqual(len(cafe_like), 2)

            consecutive_cafe_pairs = 0
            real_items = [item for item in day["items"] if item.get("itemKind") != "gap"]
            for current, nxt in zip(real_items, real_items[1:]):
                if (current.get("place") or {}).get("category") in {"cafe", "bakery"} and (nxt.get("place") or {}).get("category") in {"cafe", "bakery"}:
                    consecutive_cafe_pairs += 1
            self.assertEqual(consecutive_cafe_pairs, 0)

    def test_foodie_without_explicit_cafe_request_does_not_force_cafe_heavy_days(self) -> None:
        trip = build_itinerary(
            {
                "dates": {"start_date": "2026-06-29", "days": 3},
                "preferences": {
                    "themes": ["local"],
                    "travel_style": ["slow", "foodie", "local"],
                    "meal_preference": ["brunch", "french"],
                },
                "pace": {"level": "slow"},
                "planning_brief": {
                    "source_text": "천천히 맛집 위주로 다니고 브런치는 한 번 정도만 넣어줘. 카페 투어는 아니야.",
                    "travel_style": ["slow", "foodie", "local"],
                    "meal_preference": ["brunch", "french"],
                    "pace": "slow",
                    "strict_constraints": True,
                },
            }
        )

        self.assertTrue(
            all(
                sum(
                    1
                    for item in day["items"]
                    if (item.get("place") or {}).get("category") in {"cafe", "bakery"}
                )
                <= 2
                for day in trip["itinerary_days"]
            )
        )

    def test_build_itinerary_returns_distinct_day_story_and_night_view_fields(self) -> None:
        trip = build_itinerary(
            {
                "dates": {"start_date": "2026-06-29", "days": 4},
                "preferences": {
                    "themes": ["night_view", "art"],
                    "travel_style": ["slow"],
                    "meal_preference": ["brunch", "coffee"],
                    "night_view_required": True,
                    "must_include": ["에펠탑", "오르세"],
                },
                "pace": {"level": "slow"},
                "mobility": {"travel_mode": "both"},
                "budget": {"budget_mode": "normal"},
                "party": {"adult": 2},
            }
        )

        itinerary_days = trip["itinerary_days"]

        self.assertEqual(len(itinerary_days), 4)
        self.assertEqual(len({day["dayTheme"] for day in itinerary_days}), 4)
        self.assertIn("첫날", itinerary_days[0]["dayTheme"])
        self.assertIn("야경", itinerary_days[0]["dayTheme"])
        self.assertTrue(all(day.get("daySummary") for day in itinerary_days))
        self.assertTrue(all(day.get("routeSummary") for day in itinerary_days))
        self.assertTrue(any(item.get("isNightViewSpot") for day in itinerary_days for item in day["items"]))
        self.assertTrue(
            all(
                (item.get("place") or {}).get("category") in {"restaurant", "cafe", "bakery", "bistro", "brasserie", "bar"}
                for day in itinerary_days
                for item in day["items"]
                if item.get("time_slot") in {"lunch", "evening"} and ("점심" in item.get("title", "") or "저녁" in item.get("title", ""))
            )
        )
        self.assertTrue(
            any(
                "야경" in str(item.get("userPreferenceReason") or "")
                for day in itinerary_days
                for item in day["items"]
            )
        )
        self.assertTrue(
            all(
                item.get("timeReason")
                for day in itinerary_days
                for item in day["items"]
            )
        )
        self.assertTrue(
            all(
                item.get("role") and (item.get("place") or {}).get("role")
                for day in itinerary_days
                for item in day["items"]
            )
        )
        self.assertTrue(
            all(
                sum(
                    1
                    for item in day["items"]
                    if bool((item.get("place") or {}).get("is_cafe"))
                )
                <= 2
                for day in itinerary_days
            )
        )

    def test_strict_slow_profile_reduces_filler_slots_for_replan(self) -> None:
        trip = build_itinerary(
            {
                "dates": {"start_date": "2026-06-29", "days": 3},
                "preferences": {
                    "themes": ["night_view"],
                    "travel_style": ["slow", "cafe", "foodie"],
                    "meal_preference": ["cafe", "dessert", "french"],
                    "night_view_required": True,
                    "must_include": ["에펠탑"],
                },
                "pace": {"level": "slow"},
                "planning_brief": {
                    "must_include": ["에펠탑"],
                    "night_view_required": True,
                    "preferred_time_slots": ["evening", "night"],
                    "meal_preference": ["cafe", "dessert", "french"],
                    "travel_style": ["slow", "night_view", "foodie"],
                    "pace": "slow",
                    "strict_constraints": True,
                },
            }
        )

        self.assertTrue(all(len(day["items"]) <= 5 for day in trip["itinerary_days"]))

    def test_strict_night_view_keeps_eiffel_for_evening_slot(self) -> None:
        trip = build_itinerary(
            {
                "dates": {"start_date": "2026-06-29", "days": 3},
                "preferences": {
                    "themes": ["night_view"],
                    "travel_style": ["slow", "foodie"],
                    "meal_preference": ["french"],
                    "night_view_required": True,
                    "must_include": ["에펠탑"],
                },
                "pace": {"level": "slow"},
                "planning_brief": {
                    "must_include": ["에펠탑"],
                    "preferred_time_slots": ["evening", "night", "afternoon"],
                    "night_view_required": True,
                    "travel_style": ["night_view", "slow"],
                    "pace": "slow",
                    "strict_constraints": True,
                    "quality_focus": "reduce_helper_blocks",
                },
            }
        )

        eiffel_items = [
            item
            for day in trip["itinerary_days"]
            for item in day["items"]
            if "에펠" in str((item.get("place") or {}).get("name") or item.get("title") or "")
        ]
        self.assertTrue(eiffel_items)
        self.assertTrue(all(item.get("time_slot") in {"evening", "night"} for item in eiffel_items))

    def test_packed_profile_adds_higher_stop_density(self) -> None:
        trip = build_itinerary(
            {
                "dates": {"start_date": "2026-06-29", "days": 2},
                "preferences": {
                    "themes": ["shopping", "foodie"],
                    "travel_style": ["fast", "shopping", "foodie"],
                    "meal_preference": ["french"],
                    "must_include": ["루브르 박물관"],
                },
                "pace": {"level": "fast"},
                "planning_brief": {
                    "must_include": ["루브르 박물관"],
                    "travel_style": ["shopping", "foodie", "fast"],
                    "meal_preference": ["french"],
                    "pace": "fast",
                },
            }
        )

        self.assertTrue(all(len(day["items"]) >= 7 for day in trip["itinerary_days"]))

    def test_slow_cafe_night_view_profile_prefers_evening_blueprint(self) -> None:
        trip = build_itinerary(
            {
                "dates": {"start_date": "2026-06-29", "days": 3},
                "preferences": {
                    "themes": ["night_view"],
                    "travel_style": ["slow", "foodie", "cafe"],
                    "meal_preference": ["cafe", "dessert", "french"],
                    "night_view_required": True,
                    "must_include": ["에펠탑"],
                    "must_avoid": ["루브르 박물관"],
                },
                "pace": {"level": "slow"},
                "planning_brief": {
                    "must_include": ["에펠탑"],
                    "must_avoid": ["루브르 박물관"],
                    "preferred_time_slots": ["afternoon", "evening", "night"],
                    "meal_preference": ["cafe", "dessert", "french"],
                    "travel_style": ["slow", "night_view", "foodie", "cafe"],
                    "night_view_required": True,
                    "pace": "slow",
                    "strict_constraints": True,
                    "locked_stops": [
                        {
                            "entity": "eiffel_tower",
                            "slug": "eiffel-tower",
                            "modifier": "night_view",
                            "target_slot": "evening",
                            "locked": True,
                            "preferred_day": 1,
                            "label": "에펠탑 야경",
                        }
                    ],
                    "preferred_blueprints": ["slow_cafe_evening_day", "romantic_evening_day", "slow_cafe_day"],
                },
            }
        )

        day1 = trip["itinerary_days"][0]
        self.assertIn(day1.get("blueprintArchetype"), {"slow_cafe_evening_day", "romantic_evening_day", "night_view_focused_day"})
        eiffel_items = [item for item in day1["items"] if "에펠" in str((item.get("place") or {}).get("name") or item.get("title") or "")]
        self.assertTrue(eiffel_items)
        self.assertTrue(all(item.get("time_slot") in {"evening", "night"} for item in eiffel_items))
        self.assertTrue(any((item.get("place") or {}).get("category") in {"restaurant", "bistro", "brasserie", "bar"} for item in day1["items"] if item.get("time_slot") == "evening" and not item.get("isNightViewSpot")))


if __name__ == "__main__":
    unittest.main()
