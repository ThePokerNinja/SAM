"""Mints short-lived LiveKit access tokens for the S.A.M. client.

Phase 4: structure + health only (token minting requires livekit-api + real keys, Phase 5).
Run (Phase 5):  uvicorn server.token_server:app --port 8788
"""

from __future__ import annotations

import os

try:
    from fastapi import FastAPI, HTTPException
except Exception:  # FastAPI not installed in --mock-only setups
    FastAPI = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment,misc]


def create_app():
    if FastAPI is None:
        raise RuntimeError("Install requirements.txt to run the token server (Phase 5).")

    app = FastAPI(title="S.A.M. token server")

    @app.get("/health")
    def health() -> dict:
        configured = bool(os.getenv("LIVEKIT_API_KEY") and os.getenv("LIVEKIT_API_SECRET"))
        return {"ok": True, "livekitConfigured": configured}

    @app.post("/token")
    def token(identity: str = "user", room: str = "sam") -> dict:
        # Phase 5: build with livekit.api.AccessToken(api_key, api_secret)
        #   .with_identity(identity).with_grants(VideoGrants(room_join=True, room=room)).to_jwt()
        raise HTTPException(status_code=501, detail="Token minting is a Phase 5 stub.")

    return app


# Lazily created so importing this module never requires FastAPI.
app = create_app() if FastAPI is not None else None
