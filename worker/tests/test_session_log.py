"""Tests for optional session JSONL export (SAM-036)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sam_worker.session_log import SessionLogger, read_session_rows, session_log_enabled


def test_session_log_disabled_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SAM_SESSION_LOG", raising=False)
    monkeypatch.setenv("SAM_SESSION_LOG_DIR", str(tmp_path))
    logger = SessionLogger(room_name="demo-room", is_owner=lambda: True)
    assert logger.active is False
    assert read_session_rows(logger.path) == []


def test_session_log_writes_owner_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAM_SESSION_LOG", "1")
    monkeypatch.setenv("SAM_SESSION_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("SAM_SESSION_LOG_OWNER_ONLY", "1")
    logger = SessionLogger(room_name="owner-room", room_sid="RM_abc", is_owner=lambda: True)
    assert logger.active is True
    logger.on_conversation_item(type("Item", (), {"role": "user", "content": ["What's the pulse?"]})())
    logger.on_tools_executed(
        type(
            "Ev",
            (),
            {
                "function_calls": [
                    type("Call", (), {"name": "get_pulse", "call_id": "c1", "arguments": "{}"})()
                ],
                "function_call_outputs": [type("Out", (), {"output": '{"regime":"risk-on"}'})()],
            },
        )()
    )
    logger.close(reason="participant_left")
    rows = read_session_rows(logger.path)
    assert rows[0]["event"] == "session_start"
    assert rows[0]["is_owner"] is True
    assert any(r["event"] == "message" and r["role"] == "user" for r in rows)
    assert any(r["event"] == "tool_call" and r["name"] == "get_pulse" for r in rows)
    assert rows[-1]["event"] == "session_end"


def test_session_log_skips_non_owner_when_owner_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SAM_SESSION_LOG", "1")
    monkeypatch.setenv("SAM_SESSION_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("SAM_SESSION_LOG_OWNER_ONLY", "1")
    logger = SessionLogger(room_name="guest-room", is_owner=lambda: False)
    assert logger.active is False
    assert not logger.path.exists()


def test_session_log_allows_demo_when_owner_only_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SAM_SESSION_LOG", "1")
    monkeypatch.setenv("SAM_SESSION_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("SAM_SESSION_LOG_OWNER_ONLY", "0")
    logger = SessionLogger(room_name="demo-room", is_owner=lambda: False)
    assert logger.active is True
    logger.close()
    assert read_session_rows(logger.path)[0]["is_owner"] is False


def test_session_log_enabled_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAM_SESSION_LOG", "true")
    assert session_log_enabled() is True
    monkeypatch.delenv("SAM_SESSION_LOG", raising=False)
    assert session_log_enabled() is False
