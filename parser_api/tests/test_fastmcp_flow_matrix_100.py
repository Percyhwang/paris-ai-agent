from __future__ import annotations

import unittest
import warnings
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Callable
from unittest.mock import patch

warnings.filterwarnings(
    "ignore",
    message="authlib.jose module is deprecated, please use joserfc instead.*",
)

from parser_api.schemas import AgentRunRequest
from parser_api.services.agent_service import run_agent
from parser_api.services.profile_store import reset_user_profile, update_user_profile
from parser_api.services.trip_store import reset_trip_store, save_trip_snapshot


@dataclass(slots=True)
class FlowCase:
    name: str
    message: str
    context: dict
    expected_status: str
    expected_intent: str
    data_key: str
    expected_server: str
    expected_tool: str
    setup: Callable[[], None] | None = None
    expect_trip_id: bool = False


class FastMcpFlowMatrixBase(unittest.TestCase):
    def setUp(self) -> None:
        reset_trip_store()
        reset_user_profile()
        self._patches = ExitStack()
        self._patches.enter_context(
            patch("parser_api.parsers.create_plan.parser._call_llm_structured", return_value={})
        )
        self._patches.enter_context(
            patch("parser_api.parsers.modify_plan.parser._call_llm_structured", return_value={})
        )

    def tearDown(self) -> None:
        self._patches.close()
        reset_trip_store()
        reset_user_profile()

    def _run_flow_case(self, case: FlowCase) -> None:
        if case.setup is not None:
            case.setup()

        response = run_agent(
            AgentRunRequest(message=case.message, context=case.context)
        ).model_dump()

        self.assertEqual(response["status"], case.expected_status)
        self.assertEqual(response["intent"], case.expected_intent)
        self.assertIn(case.data_key, response["data"])
        self.assertEqual(response["data"]["meta"]["mcp"], "fastmcp")
        self.assertEqual(response["data"]["meta"]["server"], case.expected_server)
        self.assertEqual(response["data"]["meta"]["tool"], case.expected_tool)

        if case.expect_trip_id:
            self.assertTrue(response["trip_id"])


def _trip_setup_with_title(title: str) -> Callable[[], None]:
    def _setup() -> None:
        save_trip_snapshot("trip-case", title)

    return _setup


def _profile_setup_slow() -> None:
    update_user_profile({"pace_level": "slow"})


CREATE_PLAN_CASES = [
    FlowCase(
        name=f"create_plan_{index:02d}",
        message=message,
        context={},
        expected_status="DONE",
        expected_intent="CREATE_PLAN",
        data_key="plan",
        expected_server="planning-service",
        expected_tool="create_plan",
        expect_trip_id=True,
    )
    for index, message in enumerate(
        [
            "파리 3박4일 여행 계획 세워줘",
            "파리 5일 코스 구성해줘",
            "7월23일부터26일까지 파리 일정 짜줘",
            "2026년7월23일~2026년7월26일 파리 여행 계획 세워줘",
            "7월23일~26일 파리 여행 계획 세워줘",
            "혼자 파리 3박4일 여행 계획 세워줘",
            "커플 파리 3박4일 여행 짜줘",
            "친구 3명이서 파리 4일 일정 빡세게 짜줘",
            "유모차 끌고 갈거라 실내 위주로 3박4일 짜줘",
            "대중교통 위주로 환승 적게 다니고 싶어 2박3일 여행 계획 세워줘",
            "에펠탑은 꼭 넣고 3박4일 일정 짜줘",
            "가족여행 4일 일정 짜줘",
        ],
        start=1,
    )
]

MODIFY_PLAN_CASES = [
    FlowCase(
        name=f"modify_plan_{index:02d}",
        message=message,
        context={"trip_id": "trip-existing"},
        expected_status="DONE",
        expected_intent="MODIFY_PLAN",
        data_key="modify",
        expected_server="planning-service",
        expected_tool="modify_plan",
        expect_trip_id=True,
    )
    for index, message in enumerate(
        [
            "1일차 오후에 에펠탑 추가해줘",
            "1일차 오후에 루브르 빼줘",
            "1일차 오후에 루브르 대신 오르세로 바꿔줘",
            "2일차 오전이랑 오후 바꿔줘",
            "3일차 너무 빡세니까 여유롭게 바꿔줘",
            "4일차 도보 위주로 바꿔줘",
            "5일차 루브르 하나 더 넣어줘",
            "1일차 일정에서 오후에 루브르 대신 오르세로 바꿔줘",
            "현재 일정 2일차 오후에 에펠탑 추가해줘",
            "trip-existing 3일차 오후에 루브르 빼줘",
            "2일차 코스 도보 위주로 바꿔줘",
            "4일차 코스 오후에 루브르 대신 오르세로 바꿔줘",
        ],
        start=1,
    )
]

BUDGET_CASES = [
    FlowCase(
        name=f"estimate_budget_{index:02d}",
        message=message,
        context={},
        expected_status="DONE",
        expected_intent="ESTIMATE_BUDGET",
        data_key="budget_estimate",
        expected_server="discovery-service",
        expected_tool="estimate_budget",
    )
    for index, message in enumerate(
        [
            "파리 4박5일 여행 예산 계산해줘. 항공권, 호텔, 식비만 포함하고 4성급 기준으로.",
            "파리 3박4일 여행 예산 계산해줘. 호텔, 식비만 포함해줘.",
            "파리 5일 예산 계산해줘. 항공권이랑 호텔 포함.",
            "파리 2박3일 경비 계산해줘. 식비랑 교통비 포함.",
            "파리 7일 예산 계산해줘. 쇼핑 빼고 전부 포함.",
            "파리 4일 여행 비용 계산해줘. 5성급 호텔 기준으로.",
            "파리 6일 예산 계산해줘. 항공권, 식비, 액티비티 포함.",
            "파리 3일 경비 계산해줘. 교통비만 포함.",
            "파리 8일 예산 계산해줘. 호텔, 식비, 쇼핑 포함.",
            "파리 5박6일 여행 예산 계산해줘. 항공권, 호텔, 식비, 교통 포함.",
            "파리 4일 예산 계산해줘. 호텔이랑 식비만 포함해줘.",
            "파리 10일 여행 예산 계산해줘. 항공권, 호텔, 식비만 포함해줘.",
        ],
        start=1,
    )
]

ROUTE_CASES = [
    FlowCase(
        name=f"optimize_route_{index:02d}",
        message=message,
        context={},
        expected_status="DONE",
        expected_intent="OPTIMIZE_ROUTE",
        data_key="route_optimization",
        expected_server="discovery-service",
        expected_tool="optimize_route",
    )
    for index, message in enumerate(
        [
            "루브르, 오르세, 에펠탑 동선 최적화해줘. 대중교통 위주로.",
            "몽마르트, 루브르, 마레 지구 동선 최적화해줘. 도보 위주로.",
            "에펠탑, 개선문, 샹젤리제 동선 정리해줘.",
            "루브르, 오랑주리, 튈르리 정원 순서 최적화해줘.",
            "에펠탑, 세느강, 오르세 루트 최적화해줘.",
            "마레, 바스티유, 노트르담 경로 정리해줘.",
            "루브르, 생트샤펠, 노트르담 동선 최적화해줘.",
            "오르세, 앵발리드, 에펠탑 동선 최적화해줘.",
            "오페라, 갤러리 라파예트, 루브르 경로 정리해줘.",
            "몽마르트, 노트르담, 루브르 동선 최적화해줘.",
            "베르사유, 에펠탑, 개선문 동선 최적화해줘.",
            "오르세, 노트르담, 루브르 순서 최적화해줘.",
        ],
        start=1,
    )
]

RECOMMEND_CASES = [
    FlowCase(
        name=f"recommend_venue_{index:02d}",
        message=message,
        context={},
        expected_status="DONE",
        expected_intent="RECOMMEND_VENUE",
        data_key="venue_recommendation",
        expected_server="discovery-service",
        expected_tool="recommend_venue",
    )
    for index, message in enumerate(
        [
            "파리에서 분위기 좋은 카페 3곳 추천해줘",
            "파리에서 분위기 좋은 카페 5곳 추천해줘",
            "파리에서 가성비 좋은 맛집 4곳 추천해줘",
            "파리에서 로맨틱한 레스토랑 2곳 추천해줘",
            "파리에서 가족이 가기 좋은 명소 6곳 추천해줘",
            "파리에서 야경 보기 좋은 명소 3곳 추천해줘",
            "파리에서 디저트 카페 4곳 추천해줘",
            "파리에서 박물관 근처 명소 5곳 추천해줘",
            "파리에서 쇼핑 후 들르기 좋은 카페 2곳 추천해줘",
            "파리에서 마레 근처 맛집 3곳 추천해줘",
            "파리에서 에펠탑 근처 카페 4곳 추천해줘",
            "파리에서 관광지 5곳 추천해줘",
        ],
        start=1,
    )
]

MANAGE_TRIP_CASES = [
    FlowCase(
        name="manage_trip_save_01",
        message="현재 일정을 '파리 여름 여행'으로 저장해줘",
        context={},
        expected_status="DONE",
        expected_intent="MANAGE_TRIP",
        data_key="manage_trip",
        expected_server="planning-service",
        expected_tool="manage_trip",
        expect_trip_id=True,
    ),
    FlowCase(
        name="manage_trip_save_02",
        message="현재 일정을 '파리 가족 여행'으로 저장해줘",
        context={},
        expected_status="DONE",
        expected_intent="MANAGE_TRIP",
        data_key="manage_trip",
        expected_server="planning-service",
        expected_tool="manage_trip",
        expect_trip_id=True,
    ),
    FlowCase(
        name="manage_trip_list_01",
        message="저장한 일정 목록 보여줘",
        context={},
        expected_status="DONE",
        expected_intent="MANAGE_TRIP",
        data_key="manage_trip",
        expected_server="planning-service",
        expected_tool="manage_trip",
        setup=_trip_setup_with_title("리스트용 일정"),
    ),
    FlowCase(
        name="manage_trip_list_02",
        message="내 일정 리스트 보여줘",
        context={},
        expected_status="DONE",
        expected_intent="MANAGE_TRIP",
        data_key="manage_trip",
        expected_server="planning-service",
        expected_tool="manage_trip",
        setup=_trip_setup_with_title("리스트용 일정 2"),
    ),
    FlowCase(
        name="manage_trip_retrieve_01",
        message="trip-case 일정 보여줘",
        context={},
        expected_status="DONE",
        expected_intent="MANAGE_TRIP",
        data_key="manage_trip",
        expected_server="planning-service",
        expected_tool="manage_trip",
        setup=_trip_setup_with_title("조회용 일정"),
        expect_trip_id=True,
    ),
    FlowCase(
        name="manage_trip_retrieve_02",
        message="trip-case 일정 확인해줘",
        context={},
        expected_status="DONE",
        expected_intent="MANAGE_TRIP",
        data_key="manage_trip",
        expected_server="planning-service",
        expected_tool="manage_trip",
        setup=_trip_setup_with_title("조회용 일정 2"),
        expect_trip_id=True,
    ),
    FlowCase(
        name="manage_trip_rename_01",
        message="rename trip-case to 파리 가을 여행",
        context={},
        expected_status="DONE",
        expected_intent="MANAGE_TRIP",
        data_key="manage_trip",
        expected_server="planning-service",
        expected_tool="manage_trip",
        setup=_trip_setup_with_title("기존 제목"),
        expect_trip_id=True,
    ),
    FlowCase(
        name="manage_trip_rename_02",
        message="rename trip-case to 파리 겨울 여행",
        context={},
        expected_status="DONE",
        expected_intent="MANAGE_TRIP",
        data_key="manage_trip",
        expected_server="planning-service",
        expected_tool="manage_trip",
        setup=_trip_setup_with_title("기존 제목 2"),
        expect_trip_id=True,
    ),
    FlowCase(
        name="manage_trip_delete_01",
        message="delete trip-case",
        context={},
        expected_status="DONE",
        expected_intent="MANAGE_TRIP",
        data_key="manage_trip",
        expected_server="planning-service",
        expected_tool="manage_trip",
        setup=_trip_setup_with_title("삭제용 일정"),
        expect_trip_id=True,
    ),
    FlowCase(
        name="manage_trip_delete_02",
        message="remove trip-case",
        context={},
        expected_status="DONE",
        expected_intent="MANAGE_TRIP",
        data_key="manage_trip",
        expected_server="planning-service",
        expected_tool="manage_trip",
        setup=_trip_setup_with_title("삭제용 일정 2"),
        expect_trip_id=True,
    ),
    FlowCase(
        name="manage_trip_list_03",
        message="모든 일정 목록 보여줘",
        context={},
        expected_status="DONE",
        expected_intent="MANAGE_TRIP",
        data_key="manage_trip",
        expected_server="planning-service",
        expected_tool="manage_trip",
        setup=_trip_setup_with_title("전체 목록용 일정"),
    ),
    FlowCase(
        name="manage_trip_save_03",
        message="현재 일정을 '파리 봄 여행'으로 저장해줘",
        context={"trip_id": "trip-context"},
        expected_status="DONE",
        expected_intent="MANAGE_TRIP",
        data_key="manage_trip",
        expected_server="planning-service",
        expected_tool="manage_trip",
        expect_trip_id=True,
    ),
]

USER_PROFILE_CASES = [
    FlowCase(
        name=f"user_profile_{index:02d}",
        message=message,
        context={},
        expected_status="DONE",
        expected_intent="USER_PROFILE",
        data_key="user_profile",
        expected_server="profile-service",
        expected_tool="user_profile",
        setup=setup,
    )
    for index, (message, setup) in enumerate(
        [
            ("내 여행 프로필에 느긋하게 다닌다고 저장해줘", None),
            ("내 여행 프로필에 알뜰하게 여행한다고 저장해줘", None),
            ("내 여행 프로필에 쇼핑을 좋아한다고 저장해줘", None),
            ("내 여행 프로필에 야경 보는 걸 좋아한다고 저장해줘", None),
            ("내 여행 프로필에 대중교통 위주로 다닌다고 저장해줘", None),
            ("내 여행 프로필에 가족여행 취향이라고 저장해줘", None),
            ("내 여행 프로필 보여줘", _profile_setup_slow),
            ("내 프로필 보여줘", _profile_setup_slow),
            ("내 여행 프로필 확인해줘", _profile_setup_slow),
            ("내 여행 프로필에 야경 좋아한다고 저장해줘", None),
            ("내 여행 프로필에 쇼핑 좋아한다고 저장해줘", None),
            ("내 여행 프로필에 디저트 좋아한다고 저장해줘", None),
        ],
        start=1,
    )
]

TRAVEL_STYLE_CASES = [
    FlowCase(
        name=f"travel_style_{index:02d}",
        message=message,
        context={},
        expected_status="DONE",
        expected_intent="TRAVEL_STYLE",
        data_key="travel_style",
        expected_server="profile-service",
        expected_tool="travel_style",
    )
    for index, message in enumerate(
        [
            "내 여행스타일 분석해줘. 여유롭게 다니는 편이야",
            "내 여행스타일 분석해줘. 가성비를 중요하게 생각해",
            "내 여행스타일 분석해줘. 미술관 좋아해",
            "내 여행스타일 분석해줘. 야경 보는 걸 좋아해",
            "내 여행스타일 분석해줘. 쇼핑을 많이 해",
            "내 여행스타일 분석해줘. 문화 공연 좋아해",
            "내 여행스타일 분석해줘. 대중교통 위주로 다녀",
            "내 여행스타일 분석해줘. 도보 위주로 다녀",
            "내 여행스타일 분석해줘. 여유롭고 야경 좋아해",
            "내 여행스타일 분석해줘. 가성비와 야경을 좋아해",
            "내 여행스타일 분석해줘. 쇼핑을 즐기고 가성비를 중요하게 생각해",
            "내 스타일 분석해줘. 느긋하고 미술관 좋아해",
        ],
        start=1,
    )
]

TRIP_DIARY_CASES = [
    FlowCase(
        name=f"trip_diary_{index:02d}",
        message=message,
        context=context,
        expected_status="DONE",
        expected_intent="TRIP_DIARY",
        data_key="trip_diary",
        expected_server="planning-service",
        expected_tool="trip_diary",
    )
    for index, (message, context) in enumerate(
        [
            ("1일차 여행 일기 감성적으로 써줘. 루브르 메모: 첫날이라 설렜어", {}),
            ("2일차 여행 일기 감성적으로 써줘. 루브르랑 에펠탑 메모: 노을이 정말 예뻤어", {}),
            ("3일차 여행 일기 캐주얼하게 써줘. 몽마르트 메모: 골목이 예뻤어", {}),
            ("4일차 여행 일기 블로그 스타일로 써줘. 오르세 메모: 작품이 인상 깊었어", {}),
            ("5일차 여행 일기 정보형으로 써줘. 마레 메모: 동선이 좋았어", {}),
            ("1일차 여행 일기 써줘. 노트르담 메모: 사람이 많았어", {}),
            ("2일차 여행기 써줘. 에펠탑 메모: 야경이 멋졌어", {}),
            ("3일차 일기 써줘. 개선문 메모: 바람이 많이 불었어", {}),
            ("4일차 여행 일기 감성적으로 써줘. 세느강 메모: 산책이 좋았어", {}),
            ("5일차 여행 일기 블로그 스타일로 써줘. 오페라 메모: 쇼핑도 했어", {}),
            ("2일차 여행 일기 감성적으로 써줘. 루브르 메모: 비가 왔어", {"trip_id": "trip-diary"}),
            ("3일차 여행 일기 캐주얼하게 써줘. 에펠탑 메모: 사진을 많이 찍었어", {"trip_id": "trip-diary"}),
        ],
        start=1,
    )
]


ALL_CASES = (
    CREATE_PLAN_CASES
    + MODIFY_PLAN_CASES
    + BUDGET_CASES
    + ROUTE_CASES
    + RECOMMEND_CASES
    + MANAGE_TRIP_CASES
    + USER_PROFILE_CASES
    + TRAVEL_STYLE_CASES
    + TRIP_DIARY_CASES
)


class FastMcpFlowMatrixTests(FastMcpFlowMatrixBase):
    pass


def _build_test(case: FlowCase):
    def _test(self: FastMcpFlowMatrixTests) -> None:
        self._run_flow_case(case)

    _test.__name__ = f"test_{case.name}"
    return _test


for _case in ALL_CASES:
    setattr(FastMcpFlowMatrixTests, f"test_{_case.name}", _build_test(_case))
