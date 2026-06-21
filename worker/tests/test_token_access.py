from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from server.token_server import create_app


class TokenAccessGateTests(unittest.TestCase):
    def test_open_when_no_key_configured(self) -> None:
        with patch.dict(os.environ, {"LIVEKIT_URL": "", "LIVEKIT_API_KEY": "", "LIVEKIT_API_SECRET": ""}, clear=False):
            os.environ.pop("SAM_PORTAL_ACCESS_KEY", None)
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
        }
        with patch.dict(os.environ, env, clear=False):
            app = create_app()
            client = TestClient(app)
            res = client.post("/token", headers={"X-SAM-Access": "ab c/d"})
            self.assertNotEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
