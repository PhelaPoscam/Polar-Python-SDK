"""TabNet model wrapper and configuration helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
	from pytorch_tabnet.tab_model import TabNetClassifier
except ImportError:  # pragma: no cover - optional dependency
	TabNetClassifier = None


@dataclass(frozen=True)
class TabNetConfig:
	n_d: int = 41
	n_a: int = 41
	n_steps: int = 4
	gamma: float = 1.559
	lambda_sparse: float = 0.0067
	optimizer_name: str = "adam"
	optimizer_params: dict[str, Any] = field(default_factory=lambda: {"lr": 0.0088})

	def to_kwargs(self) -> dict[str, Any]:
		return {
			"n_d": self.n_d,
			"n_a": self.n_a,
			"n_steps": self.n_steps,
			"gamma": self.gamma,
			"lambda_sparse": self.lambda_sparse,
			"optimizer_fn": _resolve_optimizer(self.optimizer_name),
			"optimizer_params": dict(self.optimizer_params),
		}


def default_tabnet_config() -> TabNetConfig:
	return TabNetConfig()


def build_tabnet_classifier(config: TabNetConfig) -> Any:
	if TabNetClassifier is None:
		raise ImportError(
			"pytorch_tabnet is required. Install with: pip install pytorch-tabnet"
		)

	return TabNetClassifier(**config.to_kwargs())


def _resolve_optimizer(name: str) -> Any:
	if name.lower() != "adam":
		raise ValueError(f"Unsupported optimizer: {name}")

	try:
		import torch
	except ImportError as exc:  # pragma: no cover - optional dependency
		raise ImportError("torch is required for TabNet training") from exc

	return torch.optim.Adam
