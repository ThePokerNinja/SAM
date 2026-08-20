"""SAM-046: surface adapters. Phone and portal share one Session core."""

from __future__ import annotations

from dataclasses import dataclass

from .session import SurfaceName


@dataclass(frozen=True)
class Surface:
    name: SurfaceName
    audio_hz: int
    can_record: bool
    diarization: bool


def surface_for(name: str) -> Surface:
    if name == "phone":
        return Surface(name="phone", audio_hz=8000, can_record=False, diarization=False)
    if name == "sms":
        return Surface(name="sms", audio_hz=0, can_record=False, diarization=False)
    return Surface(name="portal", audio_hz=16000, can_record=False, diarization=True)
