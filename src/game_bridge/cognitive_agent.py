"""Cognitive agent logic (SpeedyIBL-style)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .game_connector import DifficultyProfile


class AdaptiveState(str, Enum):
	MONITOR = "MONITOR"
	ASSIST = "ASSIST"
	DE_ESCALATE = "DE_ESCALATE"
	PROVOKE = "PROVOKE"


@dataclass(frozen=True)
class CognitiveAgentConfig:
	low_arousal: float = 0.3
	high_arousal: float = 0.7
	high_performance: float = 0.7


class CognitiveAgent:
	def __init__(self, config: CognitiveAgentConfig | None = None) -> None:
		self.config = config or CognitiveAgentConfig()

	def decide_state(self, stress_score: float, performance_score: float) -> AdaptiveState:
		if stress_score >= self.config.high_arousal:
			if performance_score >= self.config.high_performance:
				return AdaptiveState.ASSIST
			return AdaptiveState.DE_ESCALATE

		if stress_score <= self.config.low_arousal:
			return AdaptiveState.PROVOKE

		return AdaptiveState.MONITOR

	def build_profile(self, state: AdaptiveState) -> DifficultyProfile:
		if state == AdaptiveState.ASSIST:
			return DifficultyProfile(spawn_rate=0.8, enemy_accuracy=0.8, game_speed=0.9)
		if state == AdaptiveState.DE_ESCALATE:
			return DifficultyProfile(spawn_rate=0.6, enemy_accuracy=0.6, game_speed=0.8)
		if state == AdaptiveState.PROVOKE:
			return DifficultyProfile(spawn_rate=1.2, enemy_accuracy=1.1, game_speed=1.1)
		return DifficultyProfile(spawn_rate=1.0, enemy_accuracy=1.0, game_speed=1.0)
