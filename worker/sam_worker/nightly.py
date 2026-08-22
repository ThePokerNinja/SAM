"""Daily Pythia calibration on a worker thread (SAM-075).

sam-agent owns the ``/var/data`` disk holding the forecast ledger, so a separate
Render cron service cannot read it. The schedule lives in the worker process
instead, next to the health listener.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

_log = logging.getLogger("sam.nightly")

DEFAULT_HOUR_UTC = 9  # ~2am Pacific: after the owner's day, before the morning brief
_FALSEY = {"0", "false", "no", "off"}


def nightly_enabled() -> bool:
    return (os.getenv("SAM_NIGHTLY_ENABLED", "") or "1").strip().lower() not in _FALSEY


def nightly_hour_utc() -> int:
    raw = (os.getenv("SAM_NIGHTLY_HOUR_UTC", "") or "").strip()
    try:
        return int(raw) % 24 if raw else DEFAULT_HOUR_UTC
    except ValueError:
        return DEFAULT_HOUR_UTC


def seconds_until(hour_utc: int, *, now: datetime | None = None) -> float:
    current = now or datetime.now(timezone.utc)
    target = current.replace(hour=hour_utc % 24, minute=0, second=0, microsecond=0)
    if target <= current:
        target += timedelta(days=1)
    return (target - current).total_seconds()


def notify_owner(candidate_id: str, summary: str) -> dict[str, Any]:
    """Post APPROVAL_NEEDED to rm_api so a nightly candidate reaches the owner."""
    from .config import Settings
    from .tools.handlers import build_rainmaker_client

    client = build_rainmaker_client(Settings.from_env())
    return asyncio.run(client.request_skill_approval(candidate_id, summary))


def run_once(notify: Any = notify_owner) -> dict[str, Any]:
    from .bench.pythia_nightly import run
    from .memory.episodic import memory_db_path

    return run(memory_db_path(), notify=notify)


def _loop(stop: threading.Event) -> None:
    while not stop.is_set():
        if stop.wait(seconds_until(nightly_hour_utc())):
            return
        try:
            _log.info("pythia nightly %s", json.dumps(run_once()))
        except Exception:  # noqa: BLE001 - a failed calibration must not kill the worker
            _log.warning("pythia nightly failed", exc_info=True)
        # Clear the target minute so one wake cannot fire the job twice.
        if stop.wait(90):
            return


def start_nightly_scheduler() -> threading.Thread | None:
    """Start the daemon thread. Returns None when disabled."""
    if not nightly_enabled():
        _log.info("pythia nightly disabled")
        return None
    thread = threading.Thread(
        target=_loop, args=(threading.Event(),), name="sam-nightly", daemon=True
    )
    thread.start()
    _log.info("pythia nightly scheduled for %02d:00 UTC", nightly_hour_utc())
    return thread
