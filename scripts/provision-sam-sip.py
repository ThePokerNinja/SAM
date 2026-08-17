"""Idempotently provision Samuel's owner-only LiveKit inbound SIP pilot."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from livekit import api

TRUNK_NAME = "Samuel pilot inbound"
RULE_NAME = "Samuel inbound"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / "worker" / ".env")
    pilot_number = _required("SAM_SIP_PILOT_NUMBER")
    auth_username = _required("SAM_SIP_AUTH_USERNAME")
    auth_password = _required("SAM_SIP_AUTH_PASSWORD")
    owner_numbers = [
        number.strip()
        for number in _required("SAM_SIP_OWNER_NUMBERS").split(",")
        if number.strip()
    ]

    client = api.LiveKitAPI(
        url=_required("LIVEKIT_URL"),
        api_key=_required("LIVEKIT_API_KEY"),
        api_secret=_required("LIVEKIT_API_SECRET"),
    )
    try:
        trunks = await client.sip.list_sip_inbound_trunk(api.ListSIPInboundTrunkRequest())
        trunk = next((item for item in trunks.items if item.name == TRUNK_NAME), None)
        if trunk is None:
            trunk = await client.sip.create_sip_inbound_trunk(
                api.CreateSIPInboundTrunkRequest(
                    trunk=api.SIPInboundTrunkInfo(
                        name=TRUNK_NAME,
                        numbers=[pilot_number],
                        allowed_numbers=owner_numbers,
                        auth_username=auth_username,
                        auth_password=auth_password,
                        krisp_enabled=True,
                    )
                )
            )
            print(f"created inbound trunk {trunk.sip_trunk_id}")
        else:
            trunk = await client.sip.update_sip_inbound_trunk(
                trunk.sip_trunk_id,
                api.SIPInboundTrunkInfo(
                    name=TRUNK_NAME,
                    numbers=[pilot_number],
                    allowed_numbers=owner_numbers,
                    auth_username=auth_username,
                    auth_password=auth_password,
                    krisp_enabled=True,
                ),
            )
            print(f"reconciled inbound trunk {trunk.sip_trunk_id}")

        rules = await client.sip.list_sip_dispatch_rule(api.ListSIPDispatchRuleRequest())
        rule = next((item for item in rules.items if item.name == RULE_NAME), None)
        if rule is None:
            rule = await client.sip.create_sip_dispatch_rule(
                api.CreateSIPDispatchRuleRequest(
                    rule=api.SIPDispatchRule(
                        dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                            room_prefix="call-"
                        )
                    ),
                    trunk_ids=[trunk.sip_trunk_id],
                    name=RULE_NAME,
                    hide_phone_number=True,
                )
            )
            print(f"created dispatch rule {rule.sip_dispatch_rule_id}")
        else:
            rule = await client.sip.update_sip_dispatch_rule_fields(
                rule.sip_dispatch_rule_id,
                trunk_ids=[trunk.sip_trunk_id],
                rule=api.SIPDispatchRule(
                    dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                        room_prefix="call-"
                    )
                ),
                name=RULE_NAME,
            )
            print(f"reconciled dispatch rule {rule.sip_dispatch_rule_id}")
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
