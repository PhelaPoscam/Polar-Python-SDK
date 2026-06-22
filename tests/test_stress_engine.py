"""Unit tests for StressEngine — UATR-style hysteresis smoother."""

import time

import pytest

from polar_ble_sdk.game_bridge.stress_engine import (
    StressEngine,
    StressSignal,
    StressState,
    UATRConfig,
)


class TestStressEngine:
    def test_initial_state_neutral(self):
        engine = StressEngine()
        assert engine.state == StressState.NEUTRAL
        assert engine.score == 0.5

    def test_single_high_signal_toward_stress(self):
        engine = StressEngine()
        engine.update(StressSignal(score=0.9, confidence=0.8))
        # After first high signal the weighted score > 0.5 but below threshold_high (0.7)
        # because exponential smoothing pulls toward mean
        assert engine.state == StressState.NEUTRAL  # not enough evidence yet

    def test_converges_to_stress(self):
        # decay=0 means score fully resets to the weighted evidence each update
        engine = StressEngine(
            UATRConfig(
                evidence_weight=1.0, decay=0.0, min_state_seconds=0.0, change_cost=0.0
            )
        )
        for _ in range(3):
            engine.update(StressSignal(score=0.8, confidence=0.9))
        assert engine.state == StressState.STRESS

    def test_converges_to_no_stress(self):
        engine = StressEngine(
            UATRConfig(
                evidence_weight=1.0, decay=0.0, min_state_seconds=0.0, change_cost=0.0
            )
        )
        for _ in range(3):
            engine.update(StressSignal(score=0.2, confidence=0.9))
        assert engine.state == StressState.NO_STRESS

    def test_hysteresis_prevents_rapid_flip(self):
        """min_state_seconds should block state changes within the cooldown window."""
        engine = StressEngine(
            UATRConfig(
                min_state_seconds=999.0, decay=0.0, evidence_weight=1.0, change_cost=0.0
            )
        )
        engine.update(StressSignal(score=0.8, confidence=0.9))
        assert engine.state == StressState.STRESS
        # Immediately send low signal — state should hold at STRESS
        engine.update(StressSignal(score=0.1, confidence=0.9))
        assert engine.state == StressState.STRESS

    def test_change_cost_blocks_near_boundary(self):
        engine = StressEngine(
            UATRConfig(
                evidence_weight=1.0, decay=1.0, min_state_seconds=0.0, change_cost=0.5
            )
        )
        engine.update(StressSignal(score=0.49, confidence=0.9))  # near boundary
        # score is ~0.49, abs(0.49-0.5)=0.01 < change_cost=0.5 → no state change
        assert engine.state == StressState.NEUTRAL

    def test_signal_resolved_time_defaults_to_now(self):
        sig = StressSignal(score=0.5, confidence=0.5)
        now = time.time()
        assert abs(sig.resolved_time() - now) < 0.1

    def test_signal_resolved_time_uses_explicit(self):
        sig = StressSignal(score=0.5, confidence=0.5, timestamp=42.0)
        assert sig.resolved_time() == 42.0
