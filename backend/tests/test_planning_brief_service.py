import unittest

from app.services.planning_brief_service import build_planning_brief, validate_planning_brief_compliance
from parser_api.parsers.create_plan.parser import parse_create_plan
from parser_api.services.place_catalog import build_itinerary


def _real_titles(itinerary_days: list[dict]) -> list[str]:
    return [
        str((item.get("place") or {}).get("name") or item.get("title") or "")
        for day in itinerary_days
        for item in day.get("items") or []
        if item.get("itemKind") != "gap"
    ]


class PlanningBriefComplianceTests(unittest.TestCase):
    def test_brief_driven_itinerary_respects_primary_user_constraints(self) -> None:
        message = (
            "파리 2박 3일 일정 짜줘. 에펠탑 야경은 꼭 보고 싶고, 루브르는 가지 않을래. "
            "하루에 너무 많이 돌아다니는 건 싫고, 카페랑 디저트 위주로 여유롭게 다니고 싶어. "
            "저녁은 분위기 좋은 프렌치 레스토랑으로 추천해줘."
        )
        parsed = parse_create_plan(message).model_dump()
        parsed["_source_message"] = message

        planning_brief = build_planning_brief(plan=parsed, intent="create_trip")
        itinerary = build_itinerary({**parsed, "planning_brief": planning_brief})
        itinerary_days = itinerary["itinerary_days"]
        validation = validate_planning_brief_compliance(itinerary_days, planning_brief)
        titles = _real_titles(itinerary_days)

        self.assertEqual(planning_brief["pace"], "slow")
        self.assertTrue(planning_brief["night_view_required"])
        self.assertTrue(planning_brief["locked_stops"])
        self.assertIn(planning_brief["preferred_blueprints"][0], {"slow_cafe_evening_day", "night_view_focused_day"})
        self.assertTrue(any("에펠" in title or "eiffel" in title.lower() for title in titles))
        self.assertTrue(all("루브르" not in title and "louvre" not in title.lower() for title in titles))
        self.assertTrue(any(item.get("isNightViewSpot") for day in itinerary_days for item in day.get("items") or []))
        self.assertFalse(validation["missing_must_include"])
        self.assertFalse(validation["included_must_avoid"])
        self.assertFalse(validation["time_slot_violations"])
        self.assertFalse(validation["pace_violations"])
        self.assertGreaterEqual(float(validation["final_quality_score"]), 0.75)

    def test_alias_matching_accepts_english_place_name_for_korean_constraints(self) -> None:
        planning_brief = {
            "must_include": ["에펠탑"],
            "must_avoid": ["루브르 박물관"],
        }
        itinerary_days = [
            {
                "day_number": 1,
                "items": [
                    {
                        "time_slot": "evening",
                        "title": "Eiffel Tower",
                        "place": {"name": "Eiffel Tower", "category": "landmark"},
                        "duration_minutes": 90,
                    }
                ],
            }
        ]

        validation = validate_planning_brief_compliance(itinerary_days, planning_brief)

        self.assertFalse(validation["missing_must_include"])
        self.assertFalse(validation["included_must_avoid"])

    def test_long_helper_blocks_trigger_quality_replan_even_if_item_kind_is_stop(self) -> None:
        planning_brief = {
            "pace": "slow",
            "must_include": ["에펠탑"],
        }
        itinerary_days = [
            {
                "day_number": 1,
                "items": [
                    {
                        "time_slot": "evening",
                        "title": "Eiffel Tower",
                        "place": {"name": "Eiffel Tower", "category": "landmark"},
                        "duration_minutes": 90,
                    },
                    {
                        "time_slot": "afternoon",
                        "title": "점심 전 자유 시간",
                        "itemKind": "stop",
                        "place": {"name": "점심 전 자유 시간", "category": "free_time"},
                        "duration_minutes": 100,
                    },
                    {
                        "time_slot": "evening",
                        "title": "저녁 전 재정비와 카페 휴식",
                        "itemKind": "stop",
                        "place": {"name": "저녁 전 재정비와 카페 휴식", "category": "free_time"},
                        "duration_minutes": 70,
                    },
                ],
            }
        ]

        validation = validate_planning_brief_compliance(itinerary_days, planning_brief)

        self.assertIn("story_flow", validation["violated_constraints"])
        self.assertTrue(validation["quality_violations"])
        self.assertTrue(validation["needs_replan"])


if __name__ == "__main__":
    unittest.main()
