from __future__ import annotations

import base64
import json
import os
import unittest
from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient

from parser_api.main import app
from parser_api.services.auth_service import reset_auth_state


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("utf-8")


def _make_google_credential(payload: dict[str, object]) -> str:
    header_segment = _b64url_encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode("utf-8"))
    payload_segment = _b64url_encode(json.dumps(payload).encode("utf-8"))
    return f"{header_segment}.{payload_segment}.signature"


class AuthApiTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_auth_state()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_auth_state()

    def test_demo_google_login_returns_user_and_tokens(self) -> None:
        response = self.client.post(
            "/api/auth/google/login",
            json={"credential": "dev:paris.traveler@example.com"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["user"]["email"], "paris.traveler@example.com")
        self.assertEqual(
            payload["data"]["user"]["google_id"],
            "dev:paris.traveler@example.com",
        )
        self.assertEqual(payload["data"]["tokens"]["token_type"], "bearer")
        self.assertTrue(payload["data"]["tokens"]["access_token"])
        self.assertTrue(payload["data"]["tokens"]["refresh_token"])

    def test_google_login_uses_google_tokeninfo_verification(self) -> None:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "aud": "google-client-id.apps.googleusercontent.com",
            "iss": "https://accounts.google.com",
            "sub": "google-user-123",
            "email": "traveler@example.com",
            "email_verified": "true",
            "exp": "4102444800",
            "name": "Paris Traveler",
            "picture": "https://example.com/avatar.png",
        }

        with patch.dict(
            os.environ,
            {"GOOGLE_CLIENT_ID": "google-client-id.apps.googleusercontent.com"},
            clear=False,
        ), patch("parser_api.services.auth_service.httpx.get", return_value=mock_response):
            response = self.client.post(
                "/api/auth/google/login",
                json={"credential": "google-id-token"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["user"]["google_id"], "google-user-123")
        self.assertEqual(payload["data"]["user"]["email"], "traveler@example.com")

    def test_google_login_falls_back_to_local_jwt_payload_when_tokeninfo_is_unreachable(self) -> None:
        credential = _make_google_credential(
            {
                "aud": "google-client-id.apps.googleusercontent.com",
                "iss": "https://accounts.google.com",
                "sub": "google-user-456",
                "email": "offline@example.com",
                "email_verified": True,
                "exp": 4102444800,
                "name": "Offline Traveler",
            }
        )

        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLIENT_ID": "google-client-id.apps.googleusercontent.com",
                "GOOGLE_AUTH_VERIFICATION_MODE": "tokeninfo_or_jwt",
            },
            clear=False,
        ), patch(
            "parser_api.services.auth_service.httpx.get",
            side_effect=httpx.ConnectError("network unreachable"),
        ):
            response = self.client.post(
                "/api/auth/google/login",
                json={"credential": credential},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["user"]["google_id"], "google-user-456")
        self.assertEqual(payload["data"]["user"]["email"], "offline@example.com")

    def test_auth_me_returns_authenticated_user(self) -> None:
        login_response = self.client.post(
            "/api/auth/google/login",
            json={"credential": "dev:me@example.com"},
        ).json()
        access_token = login_response["data"]["tokens"]["access_token"]

        response = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["email"], "me@example.com")

    def test_refresh_returns_new_token_pair(self) -> None:
        login_response = self.client.post(
            "/api/auth/google/login",
            json={"credential": "dev:refresh@example.com"},
        ).json()
        refresh_token = login_response["data"]["tokens"]["refresh_token"]
        old_access_token = login_response["data"]["tokens"]["access_token"]

        response = self.client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertNotEqual(payload["data"]["access_token"], old_access_token)
        self.assertEqual(payload["data"]["token_type"], "bearer")

    def test_auth_me_rejects_invalid_token(self) -> None:
        response = self.client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer not-a-real-token"},
        )

        self.assertEqual(response.status_code, 401)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "INVALID_TOKEN_FORMAT")

    def test_auth_routes_allow_frontend_cors_preflight(self) -> None:
        response = self.client.options(
            "/api/auth/google/login",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "POST",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "http://127.0.0.1:5173",
        )
