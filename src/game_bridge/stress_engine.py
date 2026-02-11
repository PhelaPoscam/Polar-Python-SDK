"""Stress engine implementing UATR smoothing logic."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from time import time


class StressState(str, Enum):
	NEUTRAL = "NEUTRAL"
	STRESS = "STRESS"
	NO_STRESS = "NO_STRESS"


@dataclass(frozen=True)
class UATRConfig:
	evidence_weight: float = 0.7
	decay: float = 0.9
	threshold_high: float = 0.7
	threshold_low: float = 0.3
	min_state_seconds: float = 10.0
	change_cost: float = 0.1


@dataclass
class StressSignal:
	score: float
	confidence: float
	timestamp: float | None = None

	def resolved_time(self) -> float:
		return self.timestamp if self.timestamp is not None else time()


class StressEngine:
	"""Lightweight UATR-style smoother with hysteresis and change cost."""

	def __init__(self, config: UATRConfig | None = None) -> None:
		self.config = config or UATRConfig()
		self._state = StressState.NEUTRAL
		self._score = 0.5
		self._last_change = 0.0

	@property
	def state(self) -> StressState:
		return self._state

	@property
	def score(self) -> float:
		return self._score

	def update(self, signal: StressSignal) -> StressState:
		ts = signal.resolved_time()
		weighted = self.config.evidence_weight * signal.score
		self._score = self.config.decay * self._score + (1 - self.config.decay) * weighted

		if ts - self._last_change < self.config.min_state_seconds:
			return self._state

		next_state = self._decide_state(self._score)
		if next_state != self._state:
			if abs(self._score - 0.5) >= self.config.change_cost:
				self._state = next_state
				self._last_change = ts

		return self._state

	def _decide_state(self, score: float) -> StressState:
		if score >= self.config.threshold_high:
			return StressState.STRESS
		if score <= self.config.threshold_low:
			return StressState.NO_STRESS
		return StressState.NEUTRAL
