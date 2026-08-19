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

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()  # load worker/.env so uvicorn picks up LIVEKIT_* without extra flags
except ImportError:
    pass

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from livekit import api
except ImportError:  # deps not installed in --mock-only setups
    FastAPI = None  # type: ignore[assignment]


# How long a minted token is valid for the initial join handshake.
_TOKEN_TTL_SECONDS = 600

_ACCESS_HEADER = "x-sam-access"
_DEFAULT_RM_API_BASE_URL = "https://rainmaker-api-waqs.onrender.com"


def _portal_access_required() -> bool:
    return _google_auth_required() or bool(os.getenv("SAM_PORTAL_ACCESS_KEY", "").strip())


def _google_auth_required() -> bool:
    return os.getenv("SAM_PORTAL_GOOGLE_REQUIRED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _rm_api_base_url() -> str:
    return os.getenv("RM_API_BASE_URL", _DEFAULT_RM_API_BASE_URL).strip().rstrip("/")


def _access_key_ok(request_headers: dict[str, str], query_access: str | None = None) -> bool:
    want = os.getenv("SAM_PORTAL_ACCESS_KEY", "").strip()
    if not want:
        return True
    got = (request_headers.get(_ACCESS_HEADER) or (query_access or "")).strip()
    if " " in got and "+" not in got:
        got = got.replace(" ", "+")
    return got == want


def _bearer_token(request_headers: dict[str, str]) -> str:
    raw = (request_headers.get("authorization") or "").strip()
    scheme, separator, token = raw.partition(" ")
    if not separator or scheme.lower() != "bearer":
        return ""
    return token.strip()


def _google_identity_ok(token: str) -> bool:
    """Delegate JWT and allowlist verification to rm_api; any uncertainty denies."""
    if not token or not _rm_api_base_url():
        return False
    try:
        response = httpx.get(
            f"{_rm_api_base_url()}/auth/me",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=5.0,
            follow_redirects=False,
        )
        if response.status_code != 200:
            return False
        body = response.json()
        user = body.get("user") if isinstance(body, dict) else None
        return bool(isinstance(user, dict) and str(user.get("email") or "").strip())
    except (httpx.HTTPError, ValueError, TypeError):
        return False


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
        return {
            "ok": True,
            "livekitConfigured": configured,
            "portalAccessRequired": _portal_access_required(),
            "googleAuthRequired": _google_auth_required(),
            "rmApiConfigured": bool(_rm_api_base_url()),
            "legacyAccessEnabled": bool(os.getenv("SAM_PORTAL_ACCESS_KEY", "").strip()),
        }

    @app.post("/token")
    def token(request: Request, identity: str | None = None, room: str | None = None) -> dict:
        headers = dict(request.headers)
        bearer = _bearer_token(headers)
        google_owner = _google_identity_ok(bearer)
        legacy_owner = (
            not bearer
            and not _google_auth_required()
            and _access_key_ok(headers, request.query_params.get("access"))
            and bool(os.getenv("SAM_PORTAL_ACCESS_KEY", "").strip())
        )
        if _google_auth_required() and not google_owner:
            raise HTTPException(status_code=403, detail="access_denied")
        if not _google_auth_required() and _portal_access_required() and not (
            google_owner or legacy_owner
        ):
            raise HTTPException(status_code=403, detail="access_denied")
        key = os.getenv("LIVEKIT_API_KEY")
        secret = os.getenv("LIVEKIT_API_SECRET")
        url = os.getenv("LIVEKIT_URL")
        if not (key and secret and url):
            raise HTTPException(status_code=503, detail="LiveKit not configured on the server.")

        ident = identity or f"sam-user-{uuid.uuid4().hex[:8]}"
        room_name = room or f"sam-{uuid.uuid4().hex[:12]}"

        grant = api.VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True)
        builder = (
            api.AccessToken(key, secret)
            .with_identity(ident)
            .with_name("You")
            .with_grants(grant)
            .with_ttl(timedelta(seconds=_TOKEN_TTL_SECONDS))
        )
        # Owner is minted only after rm_api verification or an explicitly enabled
        # temporary legacy-key migration. Production requires Google in render.yaml.
        if google_owner or legacy_owner:
            builder = builder.with_attributes({"role": "owner"})
        jwt = builder.to_jwt()
        return {"token": jwt, "url": url, "room": room_name, "identity": ident}

    return app


# Lazily created so importing this module never requires the optional deps.
app = create_app() if FastAPI is not None else None
