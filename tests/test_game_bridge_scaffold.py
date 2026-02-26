"""Scaffold tests for game bridge modules."""

from __future__ import annotations

from dataclasses import dataclass

from awe_polar.game_bridge.cognitive_agent import AdaptiveState, CognitiveAgent
from awe_polar.game_bridge.game_connector import DifficultyProfile, GameConnector
from awe_polar.game_bridge.stress_engine import StressEngine, StressSignal, StressState, UATRConfig


@dataclass
class DummyGameAPI:
    spawn_rate: float = 0.0
    enemy_accuracy: float = 0.0
    game_speed: float = 0.0

    def set_spawn_rate(self, value: float) -> None:
        self.spawn_rate = value

    def set_enemy_accuracy(self, value: float) -> None:
        self.enemy_accuracy = value

    def set_game_speed(self, value: float) -> None:
        self.game_speed = value


def test_stress_engine_state_transitions() -> None:
    engine = StressEngine(
        UATRConfig(min_state_seconds=0.0, decay=0.0, evidence_weight=1.0)
    )
    state = engine.update(StressSignal(score=0.9, confidence=0.9, timestamp=100.0))
    assert state == StressState.STRESS


def test_cognitive_agent_states() -> None:
    agent = CognitiveAgent()
    assert agent.decide_state(0.8, 0.8) == AdaptiveState.ASSIST
    assert agent.decide_state(0.8, 0.2) == AdaptiveState.DE_ESCALATE
    assert agent.decide_state(0.1, 0.5) == AdaptiveState.PROVOKE
    assert agent.decide_state(0.5, 0.5) == AdaptiveState.MONITOR


def test_game_connector_apply_profile() -> None:
    api = DummyGameAPI()
    connector = GameConnector(api)
    profile = DifficultyProfile(spawn_rate=1.1, enemy_accuracy=0.9, game_speed=1.0)
    connector.apply_profile(profile)
    assert api.spawn_rate == 1.1
    assert api.enemy_accuracy == 0.9
    assert api.game_speed == 1.0
