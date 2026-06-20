import unittest
from unittest.mock import patch

from app.services.plan_replanner_service import (
    _apply_early_start,
    _apply_daily_quality_repairs,
    _apply_final_anchor,
    _ensure_role_diversity,
    _llm_replanner_constraints,
    _trim_for_pace,
    _trim_for_story_quality,
    _rewrite_item_descriptions,
)


def _item(title: str, *, role: str, category: str, time_slot: str, start_time: str, description: str) -> dict:
    return {
        "id": f"item-{title}",
        "title": title,
        "role": role,
        "time_slot": time_slot,
        "start_time": start_time,
        "description": description,
        "place": {
            "name": title,
            "category": category,
            "role": role,
        },
    }


class PlanReplannerServiceTests(unittest.TestCase):
    def test_apply_early_start_promotes_non_evening_stop_to_morning(self) -> None:
        day = {
            "day_number": 1,
            "items": [
                _item("Dinner", role="dinner", category="restaurant", time_slot="evening", start_time="19:00", description="Dinner first."),
                _item("Louvre Museum", role="museum_or_gallery", category="museum", time_slot="afternoon", start_time="14:00", description="Main activity."),
                _item("Seine River Walk", role="walking_route", category="neighborhood", time_slot="night", start_time="21:00", description="Night walk."),
            ],
        }

        actions: list[dict] = []
        changed = _apply_early_start([day], actions)

        self.assertTrue(changed)
        self.assertEqual(day["items"][0]["title"], "Louvre Museum")
        self.assertEqual(day["items"][0]["time_slot"], "morning")
        self.assertEqual(day["items"][0]["start_time"], "09:15")
        self.assertEqual(actions[0]["type"], "pull_early_start")

    def test_slow_romantic_landmark_day_keeps_six_stops_during_trim_repairs(self) -> None:
        day = {
            "day_number": 1,
            "items": [
                _item("Louvre Museum", role="museum_or_gallery", category="museum", time_slot="morning", start_time="09:30", description="Museum anchor."),
                _item("Seine River Walk", role="walking_route", category="neighborhood", time_slot="afternoon", start_time="11:30", description="River walk."),
                _item("Saint-Germain Cafe", role="cafe_break", category="cafe", time_slot="afternoon", start_time="13:00", description="Coffee pause."),
                _item("La Robe et le Palais", role="dinner", category="restaurant", time_slot="evening", start_time="18:30", description="French dinner."),
                _item("Eiffel Tower", role="landmark", category="landmark", time_slot="evening", start_time="20:00", description="Night icon."),
                _item("Arc de Triomphe", role="landmark", category="landmark", time_slot="night", start_time="21:15", description="Final landmark."),
            ],
        }
        day["items"][-1]["finalAnchor"] = True
        brief = {
            "pace": "slow",
            "travel_style": ["romantic", "landmark", "classic"],
            "meal_preference": ["french", "cafe"],
            "must_include": ["에펠탑", "개선문"],
            "source_text": "커플 로맨스 랜드마크 여행",
        }

        actions: list[dict] = []
        changed_for_pace = _trim_for_pace([day], brief, actions)
        changed_for_story = _trim_for_story_quality([day], brief, actions)

        self.assertFalse(changed_for_pace)
        self.assertFalse(changed_for_story)
        self.assertEqual(len(day["items"]), 6)

    def test_apply_final_anchor_moves_target_to_trip_wide_final_position(self) -> None:
        day_one_anchor = _item(
            "Eiffel Tower",
            role="landmark",
            category="landmark",
            time_slot="afternoon",
            start_time="15:00",
            description="Classic Paris view.",
        )
        day_two_closer = _item(
            "Marais Walk",
            role="walking_route",
            category="neighborhood",
            time_slot="afternoon",
            start_time="16:00",
            description="Local walk.",
        )
        day_two_tail = _item(
            "Dinner",
            role="dinner",
            category="restaurant",
            time_slot="evening",
            start_time="19:00",
            description="Dinner stop.",
        )
        day_two_closer["finalAnchor"] = True
        itinerary_days = [
            {"day_number": 1, "items": [day_one_anchor]},
            {"day_number": 2, "items": [day_two_closer, day_two_tail]},
        ]

        actions: list[dict] = []
        changed = _apply_final_anchor(itinerary_days, {"final_anchor": "에펠탑"}, actions)

        self.assertTrue(changed)
        day_one_titles = [item["title"] for item in itinerary_days[0]["items"]]
        day_two_titles = [item["title"] for item in itinerary_days[1]["items"]]
        self.assertNotIn("Eiffel Tower", day_one_titles)
        self.assertEqual(day_two_titles[-1], "Eiffel Tower")
        self.assertTrue(itinerary_days[1]["items"][-1]["finalAnchor"])
        self.assertFalse(any(item.get("finalAnchor") for item in itinerary_days[1]["items"][:-1]))

    def test_llm_replanner_constraints_include_daily_quality_context(self) -> None:
        constraints = _llm_replanner_constraints(
            {
                "constraint_validation": {"is_valid": False},
                "planning_brief": {
                    "replan_history": [
                        {"attempt": 1, "reason": "theme_missing", "action": "rebuild"},
                        {"attempt": 2, "reason": "pace_density_mismatch", "action": "retime"},
                    ],
                    "quality_reflection": {
                        "attempt": 2,
                        "failure_types": ["theme_missing", "low_category_diversity"],
                        "failure_messages": ["The day has no clear theme."],
                        "prompt_addendum": "Fix the failed quality points below.",
                    },
                },
            },
            {
                "checks": {"daily_quality": "failed"},
                "quality_score_100": 74.0,
                "repair_suggestions": ["Add a dinner stop."],
                "failures": [
                    {
                        "type": "theme_missing",
                        "target": "day-1",
                        "message": "The day has no clear theme.",
                        "severity": "medium",
                    }
                ],
                "daily_quality": [
                    {
                        "day_number": 1,
                        "passed": False,
                        "errors": ["No clear dinner stop is scheduled."],
                        "warnings": [],
                        "repair_suggestions": ["Insert dinner."],
                        "quality_checks": {"meal_timing_ok": False},
                    }
                ],
            },
        )

        self.assertEqual(constraints["agent_evaluation"]["quality_score_100"], 74.0)
        self.assertEqual(constraints["agent_evaluation"]["failures"][0]["type"], "theme_missing")
        self.assertEqual(constraints["agent_evaluation"]["daily_quality"][0]["day_number"], 1)
        self.assertFalse(constraints["agent_evaluation"]["daily_quality"][0]["quality_checks"]["meal_timing_ok"])
        self.assertEqual(constraints["quality_reflection"]["attempt"], 2)
        self.assertEqual(len(constraints["replan_history"]), 2)

    def test_apply_daily_quality_repairs_inserts_dinner_and_rewrites_theme(self) -> None:
        itinerary_days = [
            {
                "day_number": 1,
                "title": "Classic Paris",
                "theme": "Classic Paris",
                "dayTheme": "Classic Paris",
                "items": [
                    _item(
                        "Cafe A",
                        role="cafe_break",
                        category="cafe",
                        time_slot="morning",
                        start_time="10:00",
                        description="Relaxing atmosphere and slow pace.",
                    ),
                    _item(
                        "Eiffel Tower",
                        role="landmark",
                        category="landmark",
                        time_slot="afternoon",
                        start_time="14:00",
                        description="Relaxing atmosphere and slow pace.",
                    ),
                ],
            }
        ]
        evaluation = {
            "daily_quality": [
                {
                    "day_number": 1,
                    "passed": False,
                    "quality_checks": {
                        "max_cafes_ok": True,
                        "meal_timing_ok": False,
                        "theme_exists": False,
                        "category_diversity_ok": False,
                        "main_activity_exists": True,
                        "art_day_ok": True,
                    },
                    "issue_details": [
                        {"code": "missing_dinner"},
                        {"code": "theme_missing"},
                        {"code": "generic_description_repetition"},
                        {"code": "low_category_diversity"},
                    ],
                }
            ]
        }
        dinner_place = {
            "slug": "la-robe-et-le-palais",
            "name": "La Robe et le Palais",
            "category": "restaurant",
            "coordinates": {"lat": 48.85, "lng": 2.34},
            "location": "Latin Quarter",
            "short_description": "Seasonal French dinner.",
        }
        walk_place = {
            "slug": "seine-river-walk",
            "name": "Seine River Walk",
            "category": "neighborhood",
            "coordinates": {"lat": 48.85, "lng": 2.35},
            "location": "Seine",
            "short_description": "Riverfront evening walk.",
        }

        def resolve_side_effect(query: str):
            if "Robe" in query:
                return dinner_place
            if "Seine" in query or "Luxembourg" in query:
                return walk_place
            return None

        actions: list[dict] = []
        with patch("app.services.plan_replanner_service._resolve_target_place", side_effect=resolve_side_effect):
            changed = _apply_daily_quality_repairs(itinerary_days, {"must_include": []}, evaluation, actions)

        self.assertTrue(changed)
        roles = {item.get("role") for item in itinerary_days[0]["items"]}
        self.assertIn("dinner", roles)
        self.assertGreaterEqual(len(roles), 3)
        self.assertNotEqual(itinerary_days[0]["title"], "Classic Paris")
        self.assertTrue(any(action.get("type") == "rewrite_day_theme" for action in actions))
        self.assertTrue(any(action.get("type") in {"insert_dinner", "ensure_dinner"} for action in actions))

    def test_role_diversity_breaks_consecutive_meal_blocks_with_walk(self) -> None:
        day = {
            "day_number": 1,
            "items": [
                _item("Luxembourg Gardens", role="walking_route", category="park", time_slot="morning", start_time="10:00", description="Morning walk."),
                _item("Lunch Bistro", role="lunch", category="restaurant", time_slot="lunch", start_time="12:30", description="Lunch."),
                _item("Dinner Bistro", role="dinner", category="restaurant", time_slot="evening", start_time="18:30", description="Dinner."),
            ],
        }
        walk_place = {
            "slug": "seine-river-walk",
            "name": "Seine River Walk",
            "category": "neighborhood",
            "coordinates": {"lat": 48.85, "lng": 2.35},
            "location": "Seine",
            "short_description": "Riverfront walk.",
        }
        actions: list[dict] = []

        with patch("app.services.plan_replanner_service._resolve_target_place", return_value=walk_place):
            changed = _ensure_role_diversity(day, {"pace": "slow", "must_include": []}, actions)

        self.assertTrue(changed)
        roles = [item.get("role") for item in day["items"]]
        self.assertEqual(roles, ["walking_route", "lunch", "walking_route", "dinner"])
        self.assertTrue(any(action.get("type") == "insert_walk_between_meals" for action in actions))

    def test_role_diversity_does_not_insert_cafe_without_explicit_cafe_request(self) -> None:
        day = {
            "day_number": 1,
            "items": [
                _item("Lunch Bistro", role="lunch", category="restaurant", time_slot="lunch", start_time="12:30", description="Lunch."),
                _item("Dinner Bistro", role="dinner", category="restaurant", time_slot="evening", start_time="18:30", description="Dinner."),
            ],
        }
        walk_place = {
            "slug": "seine-river-walk",
            "name": "Seine River Walk",
            "category": "neighborhood",
            "coordinates": {"lat": 48.85, "lng": 2.35},
            "location": "Seine",
            "short_description": "Riverfront walk.",
        }
        actions: list[dict] = []

        with patch("app.services.plan_replanner_service._resolve_target_place", return_value=walk_place):
            changed = _ensure_role_diversity(day, {"pace": "slow", "must_include": [], "travel_style": ["foodie"]}, actions)

        self.assertTrue(changed)
        self.assertNotIn("cafe_break", [item.get("role") for item in day["items"]])
        self.assertFalse(any(action.get("type") == "insert_cafe_support" for action in actions))

    def test_daily_quality_repair_inserts_recovery_stop_for_fatigue_issue(self) -> None:
        itinerary_days = [
            {
                "day_number": 1,
                "items": [
                    _item("Musee d'Orsay", role="museum_or_gallery", category="museum", time_slot="morning", start_time="09:45", description="Main museum."),
                    _item("Sainte-Chapelle", role="landmark", category="cathedral", time_slot="morning", start_time="10:45", description="Second heavy stop."),
                    _item("Lunch", role="lunch", category="restaurant", time_slot="lunch", start_time="12:45", description="Lunch."),
                    _item("Dinner", role="dinner", category="restaurant", time_slot="evening", start_time="18:30", description="Dinner."),
                ],
            }
        ]
        evaluation = {
            "daily_quality": [
                {
                    "day_number": 1,
                    "passed": False,
                    "quality_checks": {"recovery_rhythm_ok": False},
                    "issue_details": [{"code": "fatigue_without_break"}],
                }
            ]
        }
        cafe_place = {
            "slug": "fika",
            "name": "Fika",
            "category": "cafe",
            "coordinates": {"lat": 48.85, "lng": 2.35},
            "location": "Paris",
            "short_description": "Coffee pause.",
        }
        actions: list[dict] = []

        with patch("app.services.plan_replanner_service._resolve_target_place", return_value=cafe_place):
            changed = _apply_daily_quality_repairs(
                itinerary_days,
                {"travel_style": ["indoor", "museum"], "source_text": "실내 위주 여행", "must_include": []},
                evaluation,
                actions,
            )

        self.assertTrue(changed)
        roles = [item.get("role") for item in itinerary_days[0]["items"]]
        self.assertIn("cafe_break", roles)
        self.assertTrue(any(action.get("type") in {"insert_recovery_stop", "swap_for_recovery_stop"} for action in actions))

    def test_rewrite_item_descriptions_uses_neighboring_context(self) -> None:
        itinerary_days = [
            {
                "day_number": 1,
                "items": [
                    _item("Palais Royal", role="landmark", category="landmark", time_slot="morning", start_time="10:00", description="Generic."),
                    _item("Lunch Stop", role="lunch", category="restaurant", time_slot="lunch", start_time="12:30", description="Generic."),
                    _item("Seine Walk", role="walking_route", category="neighborhood", time_slot="afternoon", start_time="15:00", description="Generic."),
                ],
            }
        ]
        actions: list[dict] = []

        changed = _rewrite_item_descriptions(itinerary_days, actions)

        self.assertTrue(changed)
        descriptions = [item["description"] for item in itinerary_days[0]["items"]]
        self.assertEqual(len(descriptions), len(set(descriptions)))
        self.assertIn("Lunch Stop", descriptions[0])
        self.assertIn("Palais Royal", descriptions[1])
        self.assertIn("Lunch Stop", descriptions[2])


if __name__ == "__main__":
    unittest.main()
