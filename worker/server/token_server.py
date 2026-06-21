"""Mints short-lived LiveKit access tokens for the S.A.M. (Samuel) browser client.

The agent worker registers with no ``agent_name`` (automatic dispatch), so any room
a user joins gets Samuel auto-dispatched. This server only has to:
  1. mint a join token for a fresh per-session room, and
  2. tell the client which LiveKit URL to connect to.

Run locally:   uvicorn server.token_server:app --port 8788
Prod (Render):  uvicorn server.token_server:app --host 0.0.0.0 --port $PORT
Env: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, SAM_ALLOWED_ORIGINS (csv, optional).
"""

from __future__ import annotations

import os
import uuid
from datetime import timedelta

try:
    from dotenv import load_dotenv

    load_dotenv()  # load worker/.env so uvicorn picks up LIVEKIT_* without extra flags
except Exception:
    pass

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from livekit import api
except Exception:  # deps not installed in --mock-only setups
    FastAPI = None  # type: ignore[assignment]


# How long a minted token is valid for the initial join handshake.
_TOKEN_TTL_SECONDS = 600


def _allowed_origins() -> list[str]:
    raw = os.getenv("SAM_ALLOWED_ORIGINS", "").strip()
    if not raw:
        # Sensible defaults: local dev (Vite picks 5173, then 5174/5175 if busy)
        # + the prod portal domain.
        origins = ["https://voice.michaelstewman.com"]
        for port in (5173, 5174, 5175):
            origins.append(f"http://localhost:{port}")
            origins.append(f"http://127.0.0.1:{port}")
        return origins
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_app():
    if FastAPI is None:
        raise RuntimeError("Install requirements.txt to run the token server.")

    app = FastAPI(title="S.A.M. token server")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        configured = bool(
            os.getenv("LIVEKIT_API_KEY")
            and os.getenv("LIVEKIT_API_SECRET")
            and os.getenv("LIVEKIT_URL")
        )
        return {"ok": True, "livekitConfigured": configured}

    @app.post("/token")
    def token(identity: str | None = None, room: str | None = None) -> dict:
        key = os.getenv("LIVEKIT_API_KEY")
        secret = os.getenv("LIVEKIT_API_SECRET")
        url = os.getenv("LIVEKIT_URL")
        if not (key and secret and url):
            raise HTTPException(status_code=503, detail="LiveKit not configured on the server.")

        ident = identity or f"sam-user-{uuid.uuid4().hex[:8]}"
        room_name = room or f"sam-{uuid.uuid4().hex[:12]}"

        grant = api.VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True)
        jwt = (
            api.AccessToken(key, secret)
            .with_identity(ident)
            .with_name("You")
            .with_grants(grant)
            .with_ttl(timedelta(seconds=_TOKEN_TTL_SECONDS))
            .to_jwt()
        )
        return {"token": jwt, "url": url, "room": room_name, "identity": ident}

    return app


# Lazily created so importing this module never requires the optional deps.
app = create_app() if FastAPI is not None else None
