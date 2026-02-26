"""Game API connector for adaptive difficulty control."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class GameAPI(Protocol):
	def set_spawn_rate(self, value: float) -> None:
		...

	def set_enemy_accuracy(self, value: float) -> None:
		...

	def set_game_speed(self, value: float) -> None:
		...


@dataclass(frozen=True)
class DifficultyProfile:
	spawn_rate: float
	enemy_accuracy: float
	game_speed: float


class GameConnector:
	def __init__(self, api: GameAPI) -> None:
		self._api = api

	def apply_profile(self, profile: DifficultyProfile) -> None:
		self._api.set_spawn_rate(profile.spawn_rate)
		self._api.set_enemy_accuracy(profile.enemy_accuracy)
		self._api.set_game_speed(profile.game_speed)
