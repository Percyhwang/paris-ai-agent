import unittest

from parser_api.intents import Intent
from parser_api.parsers.create_plan.parser import parse_create_plan
from parser_api.parsers.modify_plan.parser import parse_modify_plan
from parser_api.services.planning_brief_service import build_unified_planning_brief


class UnifiedPlanningBriefServiceTests(unittest.TestCase):
    def test_create_plan_adapter_preserves_user_constraints(self) -> None:
        message = (
            "파리 2박 3일 일정 짜줘. 에펠탑 야경은 꼭 보고 싶고, 루브르는 가지 않을래. "
            "하루에 너무 많이 돌아다니는 건 싫고, 카페랑 디저트 위주로 여유롭게 다니고 싶어. "
            "저녁은 분위기 좋은 프렌치 레스토랑으로 추천해줘."
        )
        payload = parse_create_plan(message)

        brief = build_unified_planning_brief(Intent.CREATE_PLAN, payload, {"message": message})

        self.assertEqual(brief["intent"], "create_trip")
        self.assertEqual(brief["pace"], "slow")
        self.assertTrue(brief["night_view_required"])
        self.assertTrue(any("에펠" in value or "eiffel" in value.lower() for value in brief["must_include"]))
        self.assertTrue(any("루브르" in value or "louvre" in value.lower() for value in brief["must_avoid"]))
        self.assertTrue(any(token in {value.lower() for value in brief["meal_preference"]} for token in {"cafe", "dessert", "french"}))

    def test_modify_plan_adapter_captures_replace_intent_as_constraints(self) -> None:
        message = "day 2에는 루브르 말고 오르세 넣어줘"
        payload = parse_modify_plan(message, {"trip_id": "trip-1", "style_tags": ["slow", "night_view"], "total_days": 3})

        brief = build_unified_planning_brief(
            Intent.MODIFY_PLAN,
            payload,
            {"trip_id": "trip-1", "style_tags": ["slow", "night_view"], "total_days": 3, "message": message},
        )

        self.assertEqual(brief["intent"], "modify_trip")
        self.assertEqual(brief["pace"], "slow")
        self.assertTrue(brief["night_view_required"])
        self.assertTrue(any("오르세" in value or "orsay" in value.lower() for value in brief["must_include"]))
        self.assertTrue(any("루브르" in value or "louvre" in value.lower() for value in brief["must_avoid"]))

    def test_create_plan_adapter_keeps_late_start_brunch_as_midday_food_signal(self) -> None:
        message = "늦게 시작하는 파리 3일 여행 짜줘. 브런치 먹고 오후부터 천천히 돌아다니고 싶어."
        payload = parse_create_plan(message)

        brief = build_unified_planning_brief(Intent.CREATE_PLAN, payload, {"message": message})

        self.assertIn("brunch", brief["meal_preference"])
        self.assertNotIn("cafe", brief["travel_style"])
        self.assertIn("afternoon", brief["preferred_time_slots"])
        self.assertIn("lunch", brief["preferred_time_slots"])
        self.assertNotIn("morning", brief["preferred_time_slots"])
        self.assertEqual(brief.get("start_time"), "12:00")


if __name__ == "__main__":
    unittest.main()
