import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.routes import trips as trips_route
from app.core.config import settings
from app.main import app
from app.services.user_service import memory_user_ids_by_google_id, memory_users_by_id


class ApiSmokeTests(unittest.TestCase):
    @staticmethod
    def _patch_generate_trip(payload: dict) -> patch:
        target_name = (
            "generate_trip_with_unified_orchestrator"
            if hasattr(trips_route, "generate_trip_with_unified_orchestrator")
            else "generate_trip_payload"
        )
        return patch.object(trips_route, target_name, new=AsyncMock(return_value=payload))

    @staticmethod
    def _patch_agent_modify(payload: dict) -> patch:
        target_name = (
            "modify_trip_with_unified_orchestrator"
            if hasattr(trips_route, "modify_trip_with_unified_orchestrator")
            else "orchestrate_modify_itinerary"
        )
        return patch.object(trips_route, target_name, new=AsyncMock(return_value=payload))

    def setUp(self) -> None:
        self._original_allow_insecure_dev_auth = settings.allow_insecure_dev_auth
        settings.allow_insecure_dev_auth = True
        memory_users_by_id.clear()
        memory_user_ids_by_google_id.clear()

        self.fake_db = object()
        self._connect_patcher = patch("app.main.connect_to_mongo", new=AsyncMock())
        self._close_patcher = patch("app.main.close_mongo_connection", new=AsyncMock())
        self._connect_patcher.start()
        self._close_patcher.start()

        self._client_cm = TestClient(app)
        self.client = self._client_cm.__enter__()

    def tearDown(self) -> None:
        app.dependency_overrides = {}
        self._client_cm.__exit__(None, None, None)
        self._close_patcher.stop()
        self._connect_patcher.stop()
        memory_users_by_id.clear()
        memory_user_ids_by_google_id.clear()
        settings.allow_insecure_dev_auth = self._original_allow_insecure_dev_auth

    def _login(self) -> tuple[str, dict]:
        response = self.client.post(
            "/api/auth/google/login",
            json={"credential": "dev:smoke-login@example.com"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["success"])
        return body["data"]["tokens"]["access_token"], body["data"]["user"]

    @staticmethod
    def _auth_headers(token: str, **extra: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", **extra}

    def test_google_login_and_auth_me(self) -> None:
        access_token, user = self._login()

        response = self.client.get("/api/auth/me", headers=self._auth_headers(access_token))

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["id"], user["id"])
        self.assertEqual(body["data"]["email"], "smoke-login@example.com")

    def test_trip_generation_route_runs_after_login(self) -> None:
        access_token, user = self._login()
        app.dependency_overrides[trips_route.get_database] = lambda: self.fake_db

        generated_payload = {
            "trip": {"trip_title": "Paris Highlights"},
            "itinerary_days": [{"day_number": 1, "title": "Arrival Day", "items": []}],
            "budget": {"currency": "EUR"},
        }
        persisted_trip = {
            "id": "trip-smoke-1",
            "user_id": user["id"],
            "trip_title": "Paris Highlights",
            "prompt": "파리 3박 4일 계획 세워줘",
            "total_days": 4,
            "status": "generated",
            "style_tags": ["classic"],
            "itinerary_days": [{"day_number": 1, "title": "Arrival Day", "items": []}],
            "created_at": "2026-06-21T00:00:00+00:00",
            "updated_at": "2026-06-21T00:00:00+00:00",
        }

        with self._patch_generate_trip(generated_payload) as generate_mock, patch.object(
            trips_route,
            "create_generated_trip",
            new=AsyncMock(return_value=persisted_trip),
        ) as persist_mock:
            response = self.client.post(
                "/api/trips/generate",
                headers=self._auth_headers(access_token, **{"Accept-Language": "ko-KR"}),
                json={
                    "prompt": "파리 3박 4일 계획 세워줘",
                    "total_days": 4,
                    "style_tags": ["classic"],
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["id"], "trip-smoke-1")
        self.assertEqual(body["message"], "Trip generated")

        self.assertEqual(generate_mock.await_count, 1)
        self.assertEqual(generate_mock.await_args.args[0].prompt, "파리 3박 4일 계획 세워줘")
        self.assertEqual(generate_mock.await_args.args[0].total_days, 4)
        self.assertEqual(generate_mock.await_args.kwargs["db"], self.fake_db)
        self.assertEqual(generate_mock.await_args.kwargs["user_id"], user["id"])
        self.assertEqual(generate_mock.await_args.kwargs["language"], "ko")

        self.assertEqual(persist_mock.await_count, 1)
        self.assertEqual(persist_mock.await_args.args[0], self.fake_db)
        self.assertEqual(persist_mock.await_args.args[1], user["id"])
        self.assertEqual(persist_mock.await_args.args[2], generated_payload)

    def test_agent_modify_route_runs_after_login(self) -> None:
        access_token, user = self._login()
        app.dependency_overrides[trips_route.get_database] = lambda: self.fake_db

        modified_trip = {
            "id": "trip-smoke-1",
            "user_id": user["id"],
            "trip_title": "Paris Highlights Updated",
            "status": "modified",
            "agent_summary": "둘째 날을 더 여유롭게 조정했습니다.",
            "changed_items": [{"title": "Musee d'Orsay"}],
            "itinerary_days": [{"day_number": 2, "title": "Museum Day", "items": []}],
        }

        with self._patch_agent_modify(modified_trip) as modify_mock:
            response = self.client.post(
                "/api/trips/trip-smoke-1/agent-modify",
                headers=self._auth_headers(access_token, **{"Accept-Language": "en-US"}),
                json={"prompt": "둘째 날을 조금 더 여유롭게 바꿔줘", "target_day": 2},
            )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["message"], "Trip modified by agent")
        self.assertEqual(body["data"]["changed_items"][0]["title"], "Musee d'Orsay")

        self.assertEqual(modify_mock.await_count, 1)
        if "db" in modify_mock.await_args.kwargs:
            self.assertEqual(modify_mock.await_args.kwargs["db"], self.fake_db)
            self.assertEqual(modify_mock.await_args.kwargs["user_id"], user["id"])
            self.assertEqual(modify_mock.await_args.kwargs["trip_id"], "trip-smoke-1")
            self.assertEqual(modify_mock.await_args.kwargs["request"].prompt, "둘째 날을 조금 더 여유롭게 바꿔줘")
            self.assertEqual(modify_mock.await_args.kwargs["request"].target_day, 2)
            self.assertEqual(modify_mock.await_args.kwargs["language"], "en")
        else:
            self.assertEqual(modify_mock.await_args.args[0].prompt, "둘째 날을 조금 더 여유롭게 바꿔줘")
            self.assertEqual(modify_mock.await_args.args[0].target_day, 2)
            self.assertEqual(modify_mock.await_args.kwargs["context"]["trip_id"], "trip-smoke-1")
            self.assertEqual(modify_mock.await_args.kwargs["context"]["target_day"], 2)
            self.assertEqual(modify_mock.await_args.kwargs["context"]["language"], "en")


if __name__ == "__main__":
    unittest.main()
