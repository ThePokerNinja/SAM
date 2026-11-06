"""2026-11-05: a bare "yes" on a trading call committed a calendar change four times with none waiting."""

from __future__ import annotations

import time

import pytest

from sam_worker.session_log import prune_old_logs
from sam_worker.tools.rainmaker_registry import CALENDAR_PENDING_TTL_S, calendar_pending_fresh
from sam_worker.tools.select import is_calendar_confirm

TRADING_YESES = ["Yeah. I would.", "Yes.", "Yeah. That works."]


@pytest.mark.parametrize("line", TRADING_YESES)
def test_trading_yes_without_pending_change_never_commits(line: str) -> None:
    pending: dict = {}
    allowed = is_calendar_confirm(line) and calendar_pending_fresh(pending)
    assert not allowed


def test_yes_after_fresh_readback_commits() -> None:
    pending = {"at": time.monotonic()}
    assert is_calendar_confirm("Yes.") and calendar_pending_fresh(pending)


def test_readback_expires_after_ten_minutes() -> None:
    pending = {"at": 100.0}
    assert calendar_pending_fresh(pending, now=100.0 + CALENDAR_PENDING_TTL_S)
    assert not calendar_pending_fresh(pending, now=101.0 + CALENDAR_PENDING_TTL_S)


def test_call_logs_older_than_14_days_are_pruned(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SAM_SESSION_LOG_DAYS", raising=False)
    old, new = tmp_path / "old.jsonl", tmp_path / "new.jsonl"
    old.write_text("{}")
    new.write_text("{}")
    now = time.time()
    import os

    os.utime(old, (now - 15 * 86400, now - 15 * 86400))
    assert prune_old_logs(tmp_path, now=now) == 1
    assert new.exists() and not old.exists()
