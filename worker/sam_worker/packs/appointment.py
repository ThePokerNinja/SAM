"""SAM-055: Appointments pack helpers. Calendar tools stay in rainmaker_registry."""

from __future__ import annotations

from typing import Any


def confirm_booking(proposal: dict[str, Any], *, spoken_confirm: bool) -> dict[str, Any]:
    """Refuse to commit until the owner speaks the time back."""
    when = str(proposal.get("when") or "").strip()
    if not when or not spoken_confirm:
        return {"ok": False, "reason": "unconfirmed"}
    return {"ok": True, "when": when, "status": "booked"}
