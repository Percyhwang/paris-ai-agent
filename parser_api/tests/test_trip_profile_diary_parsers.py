import unittest

from parser_api.parsers.classifier import extract_intent
from parser_api.parsers.manage_trip.parser import parse_manage_trip
from parser_api.parsers.travel_style.parser import parse_travel_style
from parser_api.parsers.trip_diary.parser import parse_trip_diary
from parser_api.parsers.user_profile.parser import parse_user_profile
from parser_api.parsers.workflow.request_bundle.parser import parse_request_bundle
from parser_api.schemas import AgentRunRequest
from parser_api.services.agent_service import run_agent


def _assert_subset(test_case: unittest.TestCase, actual, expected) -> None:
    if isinstance(expected, dict):
        test_case.assertIsInstance(actual, dict)
        for key, value in expected.items():
            test_case.assertIn(key, actual)
            _assert_subset(test_case, actual[key], value)
        return

    if isinstance(expected, list):
        test_case.assertEqual(len(actual), len(expected))
        for actual_item, expected_item in zip(actual, expected):
            _assert_subset(test_case, actual_item, expected_item)
        return

    test_case.assertEqual(actual, expected)


class TripProfileDiaryParserTests(unittest.TestCase):
    def test_manage_trip_save_parser_builds_payload(self) -> None:
        payload = parse_manage_trip("현재 일정을 '파리 여름 여행'으로 저장해줘").model_dump()

        _assert_subset(
            self,
            payload,
            {
                "operation": "save",
                "trip_title": "파리 여름 여행",
                "clarify": {"needed": False},
            },
        )

    def test_manage_trip_rename_parser_builds_payload(self) -> None:
        payload = parse_manage_trip("trip-123 일정 제목을 파리 가족 여행으로 바꿔줘").model_dump()

        _assert_subset(
            self,
            payload,
            {
                "operation": "rename",
                "trip_id": "trip-123",
                "trip_title": "파리 가족 여행",
                "clarify": {"needed": False},
            },
        )

    def test_user_profile_parser_builds_payload(self) -> None:
        payload = parse_user_profile(
            "내 여행 프로필에 여유롭게 다니고 카페랑 맛집 위주, 4성급 호텔 선호한다고 저장해줘"
        ).model_dump()

        _assert_subset(
            self,
            payload,
            {
                "operation": "update",
                "profile": {
                    "pace_level": "slow",
                    "preferred_themes": ["foodie", "cafe"],
                    "accommodation_star_rating": 4,
                },
                "clarify": {"needed": False},
            },
        )

    def test_user_profile_retrieve_parser_builds_payload(self) -> None:
        payload = parse_user_profile("내 여행 프로필 보여줘").model_dump()

        _assert_subset(
            self,
            payload,
            {
                "operation": "retrieve",
                "clarify": {"needed": False},
            },
        )

    def test_travel_style_parser_builds_payload(self) -> None:
        payload = parse_travel_style(
            "내 여행 스타일 분석해줘. 가성비, 카페, 야경 좋아하고 여유롭게 다니는 편이야"
        ).model_dump()

        _assert_subset(
            self,
            payload,
            {
                "pace_level": "slow",
                "budget_mode": "save",
                "style_tags": ["budget", "cafe", "night_view", "slow_pace", "save_budget"],
                "venue_focus": ["cafe", "night_view"],
                "clarify": {"needed": False},
            },
        )

    def test_trip_diary_parser_builds_payload(self) -> None:
        payload = parse_trip_diary(
            "2일차 여행 일기 감성적으로 써줘. 루브르랑 에펠탑 메모: 노을이 정말 예뻤어"
        ).model_dump()

        _assert_subset(
            self,
            payload,
            {
                "target_day": 2,
                "tone": "emotional",
                "highlights": ["루브르", "에펠탑"],
                "notes": "노을이 정말 예뻤어",
                "clarify": {"needed": False},
            },
        )

    def test_trip_diary_parser_requests_scope_when_missing(self) -> None:
        payload = parse_trip_diary("여행 일기 써줘").model_dump()
        _assert_subset(
            self,
            payload,
            {
                "clarify": {"needed": True, "missing_fields": ["trip_scope"]},
            },
        )

    def test_classifier_returns_manage_trip_for_trip_list_message(self) -> None:
        intent = extract_intent("저장한 일정 목록 보여줘")
        self.assertEqual(intent.value, "MANAGE_TRIP")

    def test_request_bundle_splits_profile_and_style_actions(self) -> None:
        payload = parse_request_bundle(
            "내 여행 프로필 저장하고 여행 스타일도 분석해줘"
        ).model_dump()

        _assert_subset(
            self,
            payload,
            {
                "actions": [
                    {"intent": "USER_PROFILE", "order": 1},
                    {"intent": "TRAVEL_STYLE", "order": 2},
                ]
            },
        )

    def test_run_agent_returns_trip_diary_payload(self) -> None:
        response = run_agent(
            AgentRunRequest(
                message="2일차 여행 일기 감성적으로 써줘. 루브르랑 에펠탑",
                context={},
            )
        )

        self.assertEqual(response.status, "DONE")
        self.assertEqual(response.intent, "TRIP_DIARY")
        self.assertIn("trip_diary", response.data)
