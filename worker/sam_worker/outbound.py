"""Owner-triggered outbound SIP dial via LiveKit CreateSIPParticipant."""

from __future__ import annotations

import json
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


def is_outbound_dial_room(name: str) -> bool:
    return (name or "").startswith("samuel-dial-")


def encode_outbound_metadata(
    *,
    brief: str = "",
    guest_name: str = "",
    notify_owner: bool = True,
) -> str:
    return json.dumps(
        {
            "kind": "outbound_guest",
            "brief": (brief or "").strip(),
            "guest_name": (guest_name or "").strip(),
            "notify_owner": bool(notify_owner),
        }
    )


def decode_outbound_metadata(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw or "")
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {
        "kind": str(data.get("kind") or ""),
        "brief": str(data.get("brief") or "").strip(),
        "guest_name": str(data.get("guest_name") or "").strip(),
        "notify_owner": bool(data.get("notify_owner", True)),
    }


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
                wait_until_answered=True,
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


async def dial_from_text(
    number: str,
    *,
    brief: str = "",
    guest_name: str = "",
    notify_owner: bool = True,
) -> dict[str, Any]:
    """Mint a room, auto-dispatch Samuel, and SIP-dial the allow-listed number into it.

    SMS has no live room. This is the text adapter for ``place_call``.
    """
    import uuid

    ok, detail = can_dial(number)
    if not ok:
        return {"ok": False, "error": detail}
    room_name = f"samuel-dial-{uuid.uuid4().hex[:10]}"
    from livekit import api

    client = api.LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )
    try:
        await client.room.create_room(
            api.CreateRoomRequest(
                name=room_name,
                metadata=encode_outbound_metadata(
                    brief=brief,
                    guest_name=guest_name,
                    notify_owner=notify_owner,
                ),
            )
        )
        agent_name = (os.environ.get("SAM_AGENT_NAME") or "").strip()
        if agent_name:
            await client.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(agent_name=agent_name, room=room_name)
            )
    except Exception as exc:  # noqa: BLE001
        await client.aclose()
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)[:200]}
    await client.aclose()
    placed = await create_outbound_participant(number=detail, room_name=room_name)
    if not placed.get("ok"):
        return placed
    return {"ok": True, "number": detail, "room": room_name, **placed}
