from __future__ import annotations

import base64
import json
import os
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from server.token_server import create_app


class TokenAccessGateTests(unittest.TestCase):
    def test_open_when_no_key_configured(self) -> None:
        with patch.dict(os.environ, {"LIVEKIT_URL": "", "LIVEKIT_API_KEY": "", "LIVEKIT_API_SECRET": ""}, clear=False):
            os.environ.pop("SAM_PORTAL_ACCESS_KEY", None)
            os.environ.pop("SAM_PORTAL_GOOGLE_REQUIRED", None)
            app = create_app()
            client = TestClient(app)
            health = client.get("/health")
            self.assertEqual(health.status_code, 200)
            self.assertFalse(health.json().get("portalAccessRequired"))
            # LiveKit not configured -> 503, but not 403
            res = client.post("/token")
            self.assertNotEqual(res.status_code, 403)

    def test_requires_key_when_configured(self) -> None:
        env = {
            "LIVEKIT_URL": "",
            "LIVEKIT_API_KEY": "",
            "LIVEKIT_API_SECRET": "",
            "SAM_PORTAL_ACCESS_KEY": "test-secret-key",
            "SAM_PORTAL_GOOGLE_REQUIRED": "0",
        }
        with patch.dict(os.environ, env, clear=False):
            app = create_app()
            client = TestClient(app)
            health = client.get("/health")
            self.assertTrue(health.json().get("portalAccessRequired"))
            res = client.post("/token")
            self.assertEqual(res.status_code, 403)
            bad = client.post("/token", headers={"X-SAM-Access": "wrong"})
            self.assertEqual(bad.status_code, 403)
            res = client.post("/token", headers={"X-SAM-Access": "test-secret-key"})
            self.assertNotEqual(res.status_code, 403)
            via_query = client.post("/token?access=test-secret-key")
            self.assertNotEqual(via_query.status_code, 403)

    def test_accepts_plus_restored_from_space_in_header(self) -> None:
        env = {
            "LIVEKIT_URL": "",
            "LIVEKIT_API_KEY": "",
            "LIVEKIT_API_SECRET": "",
            "SAM_PORTAL_ACCESS_KEY": "ab+c/d",
            "SAM_PORTAL_GOOGLE_REQUIRED": "0",
        }
        with patch.dict(os.environ, env, clear=False):
            app = create_app()
            client = TestClient(app)
            res = client.post("/token", headers={"X-SAM-Access": "ab c/d"})
            self.assertNotEqual(res.status_code, 403)

    def test_google_required_fails_closed_for_absent_invalid_and_network_error(self) -> None:
        env = {
            "LIVEKIT_URL": "wss://livekit.test",
            "LIVEKIT_API_KEY": "test-key",
            "LIVEKIT_API_SECRET": "test-secret-test-secret-test-secret",
            "SAM_PORTAL_GOOGLE_REQUIRED": "1",
            "SAM_PORTAL_ACCESS_KEY": "legacy-key",
            "RM_API_BASE_URL": "https://rm.test",
        }
        with patch.dict(os.environ, env, clear=False):
            client = TestClient(create_app())
            health = client.get("/health").json()
            self.assertTrue(health["googleAuthRequired"])
            self.assertTrue(health["legacyAccessEnabled"])
            self.assertEqual(client.post("/token").status_code, 403)
            with patch("server.token_server.httpx.get") as get:
                get.return_value.status_code = 401
                self.assertEqual(
                    client.post(
                        "/token", headers={"Authorization": "Bearer invalid"}
                    ).status_code,
                    403,
                )
                get.side_effect = httpx.ConnectError("offline")
                self.assertEqual(
                    client.post(
                        "/token", headers={"Authorization": "Bearer valid-looking"}
                    ).status_code,
                    403,
                )
            # Production Google mode does not silently fall back to the legacy key.
            self.assertEqual(
                client.post("/token", headers={"X-SAM-Access": "legacy-key"}).status_code,
                403,
            )

    def test_verified_google_identity_mints_owner_attribute(self) -> None:
        env = {
            "LIVEKIT_URL": "wss://livekit.test",
            "LIVEKIT_API_KEY": "test-key",
            "LIVEKIT_API_SECRET": "test-secret-test-secret-test-secret",
            "SAM_PORTAL_GOOGLE_REQUIRED": "1",
            "RM_API_BASE_URL": "https://rm.test",
        }

        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {"user": {"email": "owner@example.com"}}

        with patch.dict(os.environ, env, clear=False), patch(
            "server.token_server.httpx.get", return_value=Response()
        ) as get:
            client = TestClient(create_app())
            response = client.post(
                "/token", headers={"Authorization": "Bearer rm-jwt"}
            )
            self.assertEqual(response.status_code, 200, response.text)
            token = response.json()["token"]
            payload_part = token.split(".")[1]
            payload_part += "=" * ((4 - len(payload_part) % 4) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_part))
            self.assertEqual(payload["attributes"]["role"], "owner")
            get.assert_called_once()
            self.assertEqual(
                get.call_args.kwargs["headers"]["Authorization"], "Bearer rm-jwt"
            )


if __name__ == "__main__":
    unittest.main()
