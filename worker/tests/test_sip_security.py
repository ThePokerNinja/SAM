from __future__ import annotations

from types import SimpleNamespace

from sam_worker.agent import sip_caller_is_authorized


def _participant(phone: str | None):
    attributes = {"sip.phoneNumber": phone} if phone is not None else {}
    return SimpleNamespace(attributes=attributes)


def test_sip_caller_accepts_normalized_owner_number() -> None:
    assert sip_caller_is_authorized(
        [_participant("+1 (555) 555-0123")],
        ("+15555550123",),
    )


def test_sip_caller_rejects_unknown_or_missing_number() -> None:
    owners = ("+15555550123",)
    assert not sip_caller_is_authorized([_participant("+15555550999")], owners)
    assert not sip_caller_is_authorized([_participant(None)], owners)
    assert not sip_caller_is_authorized([], owners)
