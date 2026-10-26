"""RM_RUNTIME fingerprint for Rainmaker Sentinel's supply-chain watch (SEC-010).

Sentinel reads this line from the Render log with a GET-only key, so it sees what
is actually running instead of what the repo declares. Nothing here calls rm_api.
Reprinted every 6 hours because a long-lived worker outlives log retention.
"""

from __future__ import annotations

import os
import platform
import ssl
import threading
import time

INTERVAL_S = 6 * 3600


def _version(dist: str) -> str:
    try:
        from importlib.metadata import version

        return version(dist)
    except Exception:  # noqa: BLE001
        return "none"


def line(service: str) -> str:
    parts = ssl.OPENSSL_VERSION.split()
    fields = {
        "service": os.environ.get("RENDER_SERVICE_NAME") or service,
        "python": platform.python_version(),
        "node": "none",
        "openssl": parts[1] if len(parts) > 1 else "none",
        "certifi": _version("certifi"),
        "image": os.environ.get("RM_BASE_IMAGE") or "none",
        "commit": os.environ.get("RENDER_GIT_COMMIT") or "none",
    }
    return "RM_RUNTIME " + " ".join(f"{k}={v}" for k, v in fields.items())


def start(service: str) -> None:
    def _loop() -> None:
        while True:
            print(line(service), flush=True)
            time.sleep(INTERVAL_S)

    threading.Thread(target=_loop, name="rm-runtime", daemon=True).start()
