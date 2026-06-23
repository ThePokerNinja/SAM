"""Per-turn latency instrumentation (PDF Phase 1 / ADR-24).

Captures the full timing profile for one voice turn so we can localize *where* a tiered target
(ADR-8) is missed - not just the v2v total. Stages LiveKit does not expose are left ``None`` and
never faked.

Design constraints:
- **Zero cost when off.** JSONL is written only when ``SAM_LATENCY_LOG=1``; otherwise this module
  just accumulates a few floats per turn.
- **Additive.** The existing v2v log line in ``agent.py`` is preserved; this is extra structure on
  top, populated from the same ``metrics_collected`` events.

Timing chain (PDF):
  user speech start -> VAD end -> STT first/final -> EOU -> LLM TTFT/complete
  -> TTS TTFB/complete -> playback start ; plus barge-in delay.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _now_ms() -> float:
    return time.time() * 1000.0


@dataclass
class TurnProfile:
    """Latency components for one ``speech_id`` (all values in milliseconds, ``None`` = not captured)."""

    speech_id: str
    # End-of-speech / turn detection.
    eou_ms: float | None = None                 # end_of_utterance_delay (dominant cost today)
    transcription_delay_ms: float | None = None  # late-STT-final diagnostic (from EOUMetrics)
    # STT.
    stt_ms: float | None = None
    # LLM.
    llm_ttft_ms: float | None = None
    llm_duration_ms: float | None = None
    # TTS.
    tts_ttfb_ms: float | None = None
    tts_duration_ms: float | None = None
    # Interruption.
    barge_in_ms: float | None = None            # user speaks over TTS -> playback stops
    # Bookkeeping.
    created_ms: float = field(default_factory=_now_ms)

    # --- the three components that make up the headline v2v number ---
    def v2v_ms(self) -> float:
        """Voice-to-voice = EOU + LLM TTFT + TTS TTFB (the components agent.py already logs)."""
        return (self.eou_ms or 0.0) + (self.llm_ttft_ms or 0.0) + (self.tts_ttfb_ms or 0.0)

    def v2v_ready(self) -> bool:
        return self.eou_ms is not None and self.llm_ttft_ms is not None and self.tts_ttfb_ms is not None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["v2v_ms"] = round(self.v2v_ms(), 1) if self.v2v_ready() else None
        return d


def latency_log_enabled() -> bool:
    return (os.environ.get("SAM_LATENCY_LOG", "") or "").strip().lower() in {"1", "true", "yes"}


def latency_log_path() -> Path:
    """JSONL destination. Honors ``SAM_LATENCY_LOG_PATH``; else a cache dir; else CWD."""
    explicit = os.environ.get("SAM_LATENCY_LOG_PATH", "").strip()
    if explicit:
        p = Path(explicit)
    else:
        base = os.environ.get("SAM_CACHE_DIR") or os.environ.get("RM_CACHE_DIR")
        root = Path(base) if base else Path.cwd()
        p = root / "latency_profiles.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def write_profile(profile: TurnProfile, *, path: Path | None = None) -> bool:
    """Append one profile as a JSONL row when logging is enabled. Returns True if written.

    Best-effort: never raises into the voice path.
    """
    if not latency_log_enabled():
        return False
    try:
        dest = path or latency_log_path()
        with dest.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(profile.to_dict(), sort_keys=True) + "\n")
        return True
    except Exception:  # noqa: BLE001 - instrumentation must never break the turn
        return False


def read_profiles(path: Path) -> list[dict]:
    """Read a JSONL latency-profile file back into dicts (used by the bench analyzer/tests)."""
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows
