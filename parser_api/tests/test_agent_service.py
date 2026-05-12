import unittest
from unittest.mock import patch

from parser_api.schemas import AgentRunRequest, AgentRunResponse, Clarify
from parser_api.services import agent_service


class AgentServiceTests(unittest.TestCase):
    def test_run_agent_returns_error_for_unimplemented_intent(self) -> None:
        request = AgentRunRequest(message="취소해줘", context={})
        response = agent_service.run_agent(request)

        self.assertEqual(response.status, "ERROR")
        self.assertEqual(response.data["code"], "NOT_IMPLEMENTED")

    def test_run_agent_delegates_to_orchestrator(self) -> None:
        request = AgentRunRequest(message="파리 여행 일정 짜줘", context={})
        expected = AgentRunResponse(
            status="ASK",
            intent="CREATE_PLAN",
            trip_id="",
            data={"plan": {"dates": {"days": None}}},
            clarify=Clarify(needed=True, missing_fields=["dates.days"]),
        )

        with patch.object(agent_service.default_orchestrator, "run", return_value=expected):
            response = agent_service.run_agent(request)

        self.assertEqual(response.status, "ASK")
        self.assertTrue(response.clarify.needed)
        self.assertEqual(response.clarify.missing_fields, ["dates.days"])
        self.assertIn("plan", response.data)
