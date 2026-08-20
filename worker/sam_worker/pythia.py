"""Pythia prediction seam (SAM-073..076). Never inline on the voice turn."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Forecast:
    subject: str
    horizon: str
    value: float
    confidence: float
    drivers: tuple[str, ...]
    provenance: str
    created_at: float = field(default_factory=time.time)

    def as_artifact(self) -> dict[str, Any]:
        return {
            "kind": "forecast",
            "subject": self.subject,
            "horizon": self.horizon,
            "value": self.value,
            "confidence": self.confidence,
            "drivers": list(self.drivers),
            "provenance": self.provenance,
        }


class BaselineStore:
    def __init__(self) -> None:
        self._values: dict[str, list[float]] = {}

    def observe(self, subject: str, value: float) -> None:
        self._values.setdefault(subject, []).append(float(value))

    def zscore(self, subject: str, value: float) -> float:
        series = self._values.get(subject) or []
        if len(series) < 2:
            return 0.0
        mean = sum(series) / len(series)
        var = sum((x - mean) ** 2 for x in series) / len(series)
        sd = math.sqrt(var) or 1.0
        return (value - mean) / sd


def predict(subject: str, horizon: str, signals: dict[str, float], baselines: BaselineStore | None = None) -> Forecast:
    """Rule/heuristic v0. Runs off the voice turn (ADR-24)."""
    keys = list(signals)
    raw = sum(signals.values()) / max(len(signals), 1)
    store = baselines or BaselineStore()
    z = store.zscore(subject, raw)
    conf = max(0.15, min(0.85, 0.4 + abs(z) * 0.1))
    return Forecast(
        subject=subject,
        horizon=horizon,
        value=raw,
        confidence=conf,
        drivers=tuple(keys[:4]),
        provenance="pythia.rule.v0",
    )


def brier(forecasts: list[tuple[float, float]]) -> float:
    """forecasts: (confidence, outcome 0/1)."""
    if not forecasts:
        return 0.0
    return sum((p - o) ** 2 for p, o in forecasts) / len(forecasts)


def maybe_trigger(forecast: Forecast, *, ready: bool) -> dict[str, Any] | None:
    """SAM-076: high-confidence x high-impact becomes a follow-up, never blocks v2v."""
    if not ready:
        return {"kind": "follow_up", "forecast": forecast.as_artifact()}
    if forecast.confidence >= 0.75:
        return {"kind": "nudge", "forecast": forecast.as_artifact()}
    return None
