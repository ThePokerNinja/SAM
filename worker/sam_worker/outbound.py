"""Owner-only outbound SIP dial via LiveKit CreateSIPParticipant."""

from __future__ import annotations

import os
import re
from typing import Any

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_e164(raw: str) -> str:
    text = (raw or "").strip()
    digits = re.sub(r"\D", "", text)
    if text.startswith("+") and _E164.match("+" + digits):
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if digits.startswith("+"):
        return "+" + digits.lstrip("+")
    return "+" + digits if digits else ""


def allowed_outbound_numbers() -> set[str]:
    raw = os.environ.get("SAM_SIP_OUTBOUND_ALLOWED", "") or os.environ.get(
        "SAM_SIP_OWNER_NUMBERS", ""
    )
    return {normalize_e164(item) for item in raw.split(",") if item.strip()}


def outbound_configured() -> bool:
    return bool(
        os.environ.get("SAM_SIP_OUTBOUND_TRUNK_ID", "").strip()
        and os.environ.get("LIVEKIT_URL", "").strip()
        and os.environ.get("LIVEKIT_API_KEY", "").strip()
        and os.environ.get("LIVEKIT_API_SECRET", "").strip()
    )


def can_dial(number: str) -> tuple[bool, str]:
    dest = normalize_e164(number)
    if not dest or not _E164.match(dest):
        return False, "invalid_number"
    allowed = allowed_outbound_numbers()
    if allowed and dest not in allowed:
        return False, "number_not_allowlisted"
    if not outbound_configured():
        return False, "outbound_not_configured"
    return True, dest


async def create_outbound_participant(
    *,
    number: str,
    room_name: str,
    identity: str = "samuel-outbound",
) -> dict[str, Any]:
    ok, detail = can_dial(number)
    if not ok:
        return {"ok": False, "error": detail}
    from livekit import api

    trunk_id = os.environ.get("SAM_SIP_OUTBOUND_TRUNK_ID", "").strip()
    client = api.LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )
    try:
        participant = await client.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=trunk_id,
                sip_call_to=detail,
                room_name=room_name,
                participant_identity=identity,
                wait_until_answered=False,
            )
        )
        return {
            "ok": True,
            "number": detail,
            "participantId": getattr(participant, "participant_id", "") or identity,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)[:200]}
    finally:
        await client.aclose()
