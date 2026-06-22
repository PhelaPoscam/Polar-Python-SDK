"""Unit tests for CognitiveAgent — SpeedyIBL-style adaptive state machine."""

from awe_polar.game_bridge.cognitive_agent import (
    AdaptiveState, CognitiveAgent, CognitiveAgentConfig,
)


class TestCognitiveAgent:
    def test_high_arousal_high_performance_assist(self):
        agent = CognitiveAgent()
        state = agent.decide_state(stress_score=0.8, performance_score=0.8)
        assert state == AdaptiveState.ASSIST

    def test_high_arousal_low_performance_de_escalate(self):
        agent = CognitiveAgent()
        state = agent.decide_state(stress_score=0.8, performance_score=0.3)
        assert state == AdaptiveState.DE_ESCALATE

    def test_low_arousal_provoke(self):
        agent = CognitiveAgent()
        state = agent.decide_state(stress_score=0.2, performance_score=0.5)
        assert state == AdaptiveState.PROVOKE

    def test_moderate_arousal_monitor(self):
        agent = CognitiveAgent()
        state = agent.decide_state(stress_score=0.5, performance_score=0.5)
        assert state == AdaptiveState.MONITOR

    def test_build_profile_monitor_default(self):
        agent = CognitiveAgent()
        profile = agent.build_profile(AdaptiveState.MONITOR)
        assert profile.spawn_rate == 1.0
        assert profile.enemy_accuracy == 1.0
        assert profile.game_speed == 1.0

    def test_build_profile_de_escalate_reduces_difficulty(self):
        agent = CognitiveAgent()
        profile = agent.build_profile(AdaptiveState.DE_ESCALATE)
        assert profile.spawn_rate < 1.0
        assert profile.enemy_accuracy < 1.0
        assert profile.game_speed < 1.0

    def test_build_profile_provoke_increases_difficulty(self):
        agent = CognitiveAgent()
        profile = agent.build_profile(AdaptiveState.PROVOKE)
        assert profile.spawn_rate > 1.0

    def test_custom_thresholds(self):
        cfg = CognitiveAgentConfig(low_arousal=0.25, high_arousal=0.75)
        agent = CognitiveAgent(cfg)
        assert agent.decide_state(0.3, 0.5) == AdaptiveState.MONITOR
        assert agent.decide_state(0.1, 0.5) == AdaptiveState.PROVOKE
