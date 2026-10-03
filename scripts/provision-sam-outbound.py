"""Idempotently create or reconcile Samuel's LiveKit **outbound** SIP trunk.

Separate from ``provision-sam-sip.py`` (inbound pilot) so the review-call rollout
can run without touching the inbound trunk or dispatch rule.

Reads ``worker/.env``:

- ``SAM_SIP_OUTBOUND_ADDRESS``  Twilio Elastic SIP termination URI host,
  e.g. ``samuel.pstn.twilio.com`` (no scheme, no ``sip:``)
- ``SAM_SIP_OUTBOUND_NUMBER``   caller ID in E.164; defaults to ``SAM_SIP_PILOT_NUMBER``
- ``SAM_SIP_AUTH_USERNAME`` / ``SAM_SIP_AUTH_PASSWORD``  the Twilio credential-list entry
- ``LIVEKIT_URL`` / ``LIVEKIT_API_KEY`` / ``LIVEKIT_API_SECRET``

Prints one machine-readable line at the end: ``SAM_SIP_OUTBOUND_TRUNK_ID=ST_...``.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from livekit import api

TRUNK_NAME = "Samuel pilot outbound"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required (worker/.env)")
    return value


def _clean_address(raw: str) -> str:
    value = raw.strip()
    for prefix in ("sip:", "sips:", "https://", "http://"):
        if value.lower().startswith(prefix):
            value = value[len(prefix):]
    return value.rstrip("/")


async def main() -> int:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / "worker" / ".env")
    address = _clean_address(_required("SAM_SIP_OUTBOUND_ADDRESS"))
    number = os.environ.get("SAM_SIP_OUTBOUND_NUMBER", "").strip() or _required("SAM_SIP_PILOT_NUMBER")
    auth_username = _required("SAM_SIP_AUTH_USERNAME")
    auth_password = _required("SAM_SIP_AUTH_PASSWORD")

    client = api.LiveKitAPI(
        url=_required("LIVEKIT_URL"),
        api_key=_required("LIVEKIT_API_KEY"),
        api_secret=_required("LIVEKIT_API_SECRET"),
    )
    try:
        existing_list = await client.sip.list_sip_outbound_trunk(api.ListSIPOutboundTrunkRequest())
        existing = next((item for item in existing_list.items if item.name == TRUNK_NAME), None)
        info = api.SIPOutboundTrunkInfo(
            name=TRUNK_NAME,
            address=address,
            numbers=[number],
            auth_username=auth_username,
            auth_password=auth_password,
        )
        if existing is None:
            trunk = await client.sip.create_sip_outbound_trunk(api.CreateSIPOutboundTrunkRequest(trunk=info))
            print(f"created outbound trunk {trunk.sip_trunk_id} -> {address} as {number}")
        else:
            trunk = await client.sip.update_sip_outbound_trunk(existing.sip_trunk_id, info)
            print(f"reconciled outbound trunk {trunk.sip_trunk_id} -> {address} as {number}")
        print(f"SAM_SIP_OUTBOUND_TRUNK_ID={trunk.sip_trunk_id}")
        return 0
    finally:
        await client.aclose()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
