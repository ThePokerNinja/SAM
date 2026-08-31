"""Hard caps on granted demo and moderate rooms (Platform 3.0 Phase 5a).

Join already consumes one minute. Each guest or host turn consumes another
chunk. A 409 from rm_api means expired or over cap — hang up, do not retry.
Network errors stay soft so a blip does not end the walkthrough.
"""

from __future__ import annotations

from typing import Any

CAPPED_PREFIXES = ("demo-", "intake-", "mod-")
TURN_MINUTES = 1.0
TURN_TOKENS = 80
GOODBYE = (
    "That's our time on this walkthrough. "
    "Michael can grant another if you want to keep going."
)
_HANGUP_ERRORS = frozenset(
    {"http_409", "minutes_cap", "tokens_cap", "expired", "unknown_room", "cap"}
)


def is_capped_room(room_name: str) -> bool:
    name = (room_name or "").lower()
    # Owner proposal-builder rooms are not granted-demo caps.
    if name.startswith("demo-builder-") or name.startswith("builder-"):
        return False
    return name.startswith(CAPPED_PREFIXES)


def should_hangup(tick_result: dict[str, Any] | None) -> bool:
    if not tick_result or tick_result.get("ok"):
        return False
    err = str(tick_result.get("error") or "").strip().lower()
    return err in _HANGUP_ERRORS or err.startswith("http_409")
