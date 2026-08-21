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
                    hide_phone_number=False,
                )
            )
            print(f"created dispatch rule {rule.sip_dispatch_rule_id}")
        else:
            rule = await client.sip.update_sip_dispatch_rule(
                rule.sip_dispatch_rule_id,
                api.SIPDispatchRuleInfo(
                    sip_dispatch_rule_id=rule.sip_dispatch_rule_id,
                    name=RULE_NAME,
                    trunk_ids=[trunk.sip_trunk_id],
                    hide_phone_number=False,
                    rule=api.SIPDispatchRule(
                        dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                            room_prefix="call-"
                        )
                    ),
                ),
            )
            print(f"reconciled dispatch rule {rule.sip_dispatch_rule_id}")

        outbound_address = os.environ.get("SAM_SIP_OUTBOUND_ADDRESS", "").strip()
        if outbound_address:
            outbound_name = "Samuel pilot outbound"
            outbound_number = os.environ.get("SAM_SIP_OUTBOUND_NUMBER", "").strip() or _required(
                "SAM_SIP_PILOT_NUMBER"
            )
            trunks_out = await client.sip.list_sip_outbound_trunk(
                api.ListSIPOutboundTrunkRequest()
            )
            existing = next(
                (item for item in trunks_out.items if item.name == outbound_name), None
            )
            info = api.SIPOutboundTrunkInfo(
                name=outbound_name,
                address=outbound_address,
                numbers=[outbound_number],
                auth_username=auth_username,
                auth_password=auth_password,
            )
            if existing is None:
                created = await client.sip.create_sip_outbound_trunk(
                    api.CreateSIPOutboundTrunkRequest(trunk=info)
                )
                print(f"created outbound trunk {created.sip_trunk_id}")
            else:
                updated = await client.sip.update_sip_outbound_trunk(
                    existing.sip_trunk_id, info
                )
                print(f"reconciled outbound trunk {updated.sip_trunk_id}")
        else:
            print("SAM_SIP_OUTBOUND_ADDRESS unset; skipped outbound trunk")
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
