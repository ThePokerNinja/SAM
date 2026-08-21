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


class _HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] not in ("/health", "/"):
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(health_payload()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


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
