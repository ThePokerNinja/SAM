from __future__ import annotations

import pytest

from sam_worker.config import Settings, turn_mode_from_env
from sam_worker.turns import build_turn_handling


@pytest.mark.parametrize("mode", ["cloud", "mini", "vad", "stt"])
def test_all_turn_modes_use_new_turn_handling(mode) -> None:
    settings = Settings(turn_mode=mode)
    options = build_turn_handling(settings)
    detector = options["turn_detection"]
    if mode in {"vad", "stt"}:
        assert detector == mode
    else:
        assert getattr(detector, "model", "").startswith("turn-detector-v1")
        if mode == "mini":
            assert detector.model == "turn-detector-v1-mini"
    assert options["endpointing"]["mode"] == "dynamic"
    assert options["endpointing"]["min_delay"] == 0.25
    assert options["endpointing"]["max_delay"] == 0.6
    assert options["preemptive_generation"]["preemptive_tts"] is True
    assert options["interruption"]["enabled"] is True


def test_invalid_turn_mode_falls_back_to_cloud(monkeypatch) -> None:
    monkeypatch.setenv("SAM_TURN_MODE", "fastest")
    with pytest.warns(RuntimeWarning, match="falling back to cloud"):
        assert turn_mode_from_env() == "cloud"


def test_invalid_endpoint_range_fails() -> None:
    with pytest.raises(ValueError, match="endpoint"):
        build_turn_handling(Settings(endpoint_min=1.0, endpoint_max=0.5))


def test_vad_interruption_mode_is_selectable() -> None:
    options = build_turn_handling(Settings(interruption_mode="vad"))
    assert options["interruption"]["mode"] == "vad"
