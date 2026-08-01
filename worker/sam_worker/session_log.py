"""Optional per-room session transcript export (SAM-036 / Wave 1 OS).

When ``SAM_SESSION_LOG=1``, append JSONL rows for each voice/chat turn and tool call so
we can audit hallucinations and replay demo QA offline. Zero cost when off.

Retention: set ``SAM_SESSION_LOG_OWNER_ONLY=1`` (default) to write logs only for owner
sessions (portal access-key + voice verify). Non-owner joins are skipped entirely.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


def _now_ms() -> float:
    return time.time() * 1000.0


def _truthy(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def session_log_enabled() -> bool:
    return _truthy("SAM_SESSION_LOG")


def session_log_owner_only() -> bool:
    return _truthy("SAM_SESSION_LOG_OWNER_ONLY", default=True)


def session_log_dir() -> Path:
    explicit = os.environ.get("SAM_SESSION_LOG_DIR", "").strip()
    if explicit:
        root = Path(explicit)
    else:
        base = os.environ.get("SAM_CACHE_DIR") or os.environ.get("RM_CACHE_DIR")
        root = Path(base) if base else Path.cwd()
        root = root / "sessions"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_room_slug(room_name: str) -> str:
    slug = re.sub(r"[^\w.\-]+", "_", room_name.strip())[:120]
    return slug or "room"


def _truncate(value: Any, limit: int = 4000) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"...[+{len(value) - limit}]"
    return value


def _message_text(item: Any) -> str:
    parts: list[str] = []
    for chunk in getattr(item, "content", []) or []:
        if isinstance(chunk, str):
            parts.append(chunk)
        elif hasattr(chunk, "text"):
            parts.append(str(getattr(chunk, "text", "")))
        elif isinstance(chunk, dict) and chunk.get("text"):
            parts.append(str(chunk["text"]))
    return " ".join(p.strip() for p in parts if p and str(p).strip())


@dataclass
class SessionLogger:
    """Best-effort JSONL writer for one LiveKit room. Never raises into the voice path."""

    room_name: str
    room_sid: str = ""
    is_owner: Callable[[], bool] = field(default=lambda: False)
    _active: bool = field(init=False)
    _path: Path = field(init=False)

    def __post_init__(self) -> None:
        self._active = False
        self._path = session_log_dir() / f"{_safe_room_slug(self.room_name)}.jsonl"
        if not session_log_enabled():
            return
        owner = self.is_owner()
        if session_log_owner_only() and not owner:
            return
        self._active = True
        self.write(
            "session_start",
            room=self.room_name,
            room_sid=self.room_sid,
            is_owner=owner,
            owner_only=session_log_owner_only(),
        )

    @property
    def active(self) -> bool:
        return self._active

    @property
    def path(self) -> Path:
        return self._path

    def write(self, event: str, **fields: Any) -> bool:
        if not self._active:
            return False
        row = {"event": event, "ts_ms": round(_now_ms(), 1), **fields}
        try:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
            return True
        except Exception:  # noqa: BLE001
            return False

    def on_conversation_item(self, item: Any) -> None:
        role = getattr(item, "role", None)
        if role not in {"user", "assistant", "system", "developer"}:
            return
        text = _message_text(item)
        if not text:
            return
        self.write(
            "message",
            role=role,
            text=_truncate(text),
            message_id=getattr(item, "id", None),
            interrupted=getattr(item, "interrupted", False),
            confidence=getattr(item, "transcript_confidence", None),
        )

    def on_user_transcript(self, *, transcript: str, is_final: bool, speaker_id: str | None) -> None:
        if not is_final or not transcript.strip():
            return
        self.write(
            "transcript",
            text=_truncate(transcript.strip()),
            is_final=True,
            speaker_id=speaker_id,
        )

    def on_tools_executed(self, ev: Any) -> None:
        calls = getattr(ev, "function_calls", None) or []
        outputs = getattr(ev, "function_call_outputs", None) or []
        for call, output in zip(calls, outputs, strict=False):
            out_text = ""
            if output is not None:
                out_text = getattr(output, "output", None) or getattr(output, "content", "") or ""
                if not isinstance(out_text, str):
                    out_text = str(out_text)
            self.write(
                "tool_call",
                name=getattr(call, "name", None),
                call_id=getattr(call, "call_id", None),
                arguments=_truncate(getattr(call, "arguments", "") or ""),
                output=_truncate(out_text),
            )

    def close(self, *, reason: str = "", error: str | None = None) -> None:
        if not self._active:
            return
        self.write("session_end", reason=reason or "close", error=error)
        self._active = False


def read_session_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows
