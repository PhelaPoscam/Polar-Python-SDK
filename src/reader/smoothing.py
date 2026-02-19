"""Optional smoothing bridge for reader predictions."""

from __future__ import annotations

from dataclasses import dataclass

from game_bridge.stress_engine import StressEngine, StressSignal, StressState


@dataclass
class SmoothedPrediction:
    label: str
    score: float
    confidence: float
    state: StressState


def apply_smoothing(
    engine: StressEngine,
    score: float,
    confidence: float,
    label: str,
) -> SmoothedPrediction:
    state = engine.update(StressSignal(score=score, confidence=confidence))
    return SmoothedPrediction(label=label, score=score, confidence=confidence, state=state)
