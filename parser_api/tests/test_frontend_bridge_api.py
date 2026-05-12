from __future__ import annotations

import base64
import json
import os
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from parser_api.main import app
from parser_api.services.auth_service import USER_BY_GOOGLE_ID, USER_STATE
from parser_api.services.frontend_store import reset_frontend_store
from parser_api.services.profile_store import reset_user_profile
from parser_api.services.trip_store import reset_trip_store


def _b64url(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("utf-8")


def _fake_google_jwt() -> str:
    client_id = (
        os.environ.get("GOOGLE_CLIENT_ID")
        or os.environ.get("VITE_GOOGLE_CLIENT_ID")
        or "local-dev-client-id"
    )
    header = {"alg": "none", "typ": "JWT"}
    payload = {
        "sub": "google-user-123",
        "email": "traveler@example.com",
        "name": "Paris Traveler",
        "picture": "https://example.com/avatar.png",
        "iss": "https://accounts.google.com",
        "email_verified": True,
        "aud": client_id,
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    return f"{_b64url(header)}.{_b64url(payload)}.signature"


class FrontendBridgeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["ALLOW_INSECURE_DEV_AUTH"] = "true"
        self.client = TestClient(app)
        reset_trip_store()
        reset_user_profile()
        reset_frontend_store()
        USER_STATE.clear()
        USER_BY_GOOGLE_ID.clear()
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
        reset_frontend_store()
        USER_STATE.clear()
        USER_BY_GOOGLE_ID.clear()

    def test_google_login_accepts_insecure_dev_google_payload(self) -> None:
        response = self.client.post("/api/auth/google/login", json={"credential": _fake_google_jwt()})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["user"]["email"], "traveler@example.com")
        self.assertIn("access_token", body["data"]["tokens"])

    def test_generate_trip_and_get_trip(self) -> None:
        generate = self.client.post(
            "/api/trips/generate",
            json={"prompt": "파리 3박4일 여행 계획 세워줘"},
        )
        self.assertEqual(generate.status_code, 200)
        trip = generate.json()["data"]
        self.assertEqual(trip["trip_title"], "Paris 4일 여행")
        self.assertEqual(trip["total_days"], 4)
        self.assertTrue(trip["itinerary_days"])
        self.assertNotIn("파리 산책", [item["title"] for item in trip["itinerary_days"][0]["items"]])
        self.assertTrue(trip["itinerary_days"][0]["items"][0]["place"]["coordinates"])
        self.assertIn("데이터 기반", trip["route_summary"])

        fetched = self.client.get(f"/api/trips/{trip['id']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["data"]["id"], trip["id"])

    def test_budget_diary_and_reservation_endpoints(self) -> None:
        trip = self.client.post(
            "/api/trips/generate",
            json={"prompt": "파리 2박3일 여행 계획 세워줘"},
        ).json()["data"]
        trip_id = trip["id"]

        budget = self.client.get(f"/api/trips/{trip_id}/budget")
        self.assertEqual(budget.status_code, 200)
        self.assertGreater(budget.json()["data"]["grand_total"], 0)

        generated = self.client.post(
            f"/api/trips/{trip_id}/diary/generate",
            json={
                "entry_date": "2026-05-12",
                "photo_urls": [],
                "emotion_tags": ["설렘", "낭만"],
                "notes": "노을이 정말 예뻤어",
                "place": "에펠탑",
            },
        )
        self.assertEqual(generated.status_code, 200)
        self.assertIn("generated_diary_text", generated.json()["data"])

        saved = self.client.post(
            f"/api/trips/{trip_id}/diary",
            json={
                "entry_date": "2026-05-12",
                "photo_urls": [],
                "emotion_tags": ["설렘", "낭만"],
                "notes": "노을이 정말 예뻤어",
                "place": "에펠탑",
                "title": "에펠탑 저녁",
                "generated_diary_text": "에펠탑 저녁이 정말 아름다웠다.",
                "mood_keywords": ["설렘", "낭만"],
            },
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["data"]["trip_id"], trip_id)

        reservation = self.client.post(
            f"/api/trips/{trip_id}/reservations",
            json={
                "reservation_type": "hotel",
                "provider": "Manual",
                "title": "호텔 메모",
                "start_date": "2026-07-10",
                "end_date": "2026-07-13",
                "price": 300,
                "currency": "EUR",
                "status": "pending",
                "booking_reference": "NOTE-1",
            },
        )
        self.assertEqual(reservation.status_code, 200)
        self.assertEqual(reservation.json()["data"]["reservation_type"], "hotel")

    def test_places_and_weather_endpoints(self) -> None:
        places = self.client.get("/api/places?search=루브르&category=museum&sort=popular")
        self.assertEqual(places.status_code, 200)
        self.assertTrue(places.json()["data"])
        self.assertEqual(places.json()["data"][0]["name"], "루브르 박물관")

        forecast = self.client.get("/api/weather/paris/forecast?days=5")
        self.assertEqual(forecast.status_code, 200)
        self.assertEqual(len(forecast.json()["data"]["days"]), 5)

    def test_generate_trip_memorable_transit_prompt_uses_curated_route(self) -> None:
        generate = self.client.post(
            "/api/trips/generate",
            json={"prompt": "7월3일부터 11일까지 친구들이랑 파리러로 여행을 가는데 대중교통을 이용할거야 기억에 남는 파리 여행 계획 만들어줘"},
        )
        self.assertEqual(generate.status_code, 200)
        trip = generate.json()["data"]
        self.assertIn("transit", trip["style_tags"])
        first_day_items = trip["itinerary_days"][0]["items"]
        self.assertTrue(all(item["place"]["place_id"] for item in first_day_items))
        self.assertTrue(all(not str(item["place"]["place_id"]).startswith("osm-") for item in first_day_items))
