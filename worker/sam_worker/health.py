"""Tiny HTTP health listener for the LiveKit worker (sam-agent has no public URL).

Render private services are reachable on the internal network. Bind
SAM_HEALTH_PORT (default 8080) so rainmaker-api and operators can poll
git SHA + live env without archaeology.
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

_STARTED_AT = time.time()


def health_payload() -> dict[str, Any]:
    git = (
        os.environ.get("RENDER_GIT_COMMIT")
        or os.environ.get("SAM_GIT_COMMIT")
        or ""
    ).strip()
    return {
        "ok": True,
        "service": "sam-agent",
        "git": git,
        "brain": os.environ.get("SAM_BRAIN", ""),
        "turnMode": os.environ.get("SAM_TURN_MODE", ""),
        "endpointingMax": os.environ.get("SAM_ENDPOINTING_MAX", ""),
        "groqModel": os.environ.get("GROQ_MODEL", ""),
        "uptimeSec": int(time.time() - _STARTED_AT),
    }


def hero_snapshot_payload() -> dict[str, Any]:
    """SAM-058: the live character sheet rm_api fetches for the HERO card."""
    from .skillbuilder.runtime import SkillBuilderRuntime
    from .skillbuilder.snapshot import live_snapshot

    return live_snapshot(SkillBuilderRuntime())


class _HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _write(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        route = self.path.split("?", 1)[0]
        if route in ("/health", "/"):
            self._write(200, health_payload())
            return
        if route == "/hero":
            try:
                self._write(200, hero_snapshot_payload())
            except Exception:  # noqa: BLE001 - rm_api falls back to its local sheet
                self._write(503, {"ok": False, "error": "snapshot_unavailable"})
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        route = self.path.split("?", 1)[0]
        if route != "/dial":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            self._write(400, {"ok": False, "error": "invalid_json"})
            return
        number = str((payload or {}).get("number") or "").strip()
        if not number:
            self._write(400, {"ok": False, "error": "number_required"})
            return
        import asyncio

        from .outbound import dial_from_text

        try:
            result = asyncio.run(dial_from_text(number))
        except Exception:  # noqa: BLE001
            self._write(500, {"ok": False, "error": "dial_failed"})
            return
        self._write(200 if result.get("ok") else 409, result)


def start_health_server(port: int | None = None) -> ThreadingHTTPServer | None:
    """Start a daemon thread. Returns the server, or None if bind fails."""
    resolved = int(
        port
        if port is not None
        else (os.environ.get("SAM_HEALTH_PORT") or "8080")
    )
    try:
        server = ThreadingHTTPServer(("0.0.0.0", resolved), _HealthHandler)
    except OSError:
        return None
    thread = threading.Thread(target=server.serve_forever, name="sam-health", daemon=True)
    thread.start()
    return server
