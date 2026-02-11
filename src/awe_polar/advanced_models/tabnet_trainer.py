"""Training loop with LOSO validation for TabNet."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from .tabnet_model import TabNetConfig, build_tabnet_classifier


@dataclass(frozen=True)
class TrainingConfig:
	feature_columns: list[str]
	label_column: str
	subject_column: str
	tabnet_config: TabNetConfig = TabNetConfig()


@dataclass
class FoldResult:
	subject_id: str
	metrics: dict[str, float]
	model: Any | None = None


def run_loso_training(
	df: pd.DataFrame,
	config: TrainingConfig,
	train_fn: Callable[[np.ndarray, np.ndarray, np.ndarray, np.ndarray, TabNetConfig], Any] | None = None,
) -> list[FoldResult]:
	"""Run LOSO cross-validation using a pluggable train function."""
	if train_fn is None:
		train_fn = _default_train_fn

	folds: list[FoldResult] = []
	for subject_id in df[config.subject_column].astype(str).unique():
		train_df = df[df[config.subject_column].astype(str) != subject_id]
		test_df = df[df[config.subject_column].astype(str) == subject_id]
		X_train, y_train, X_test, y_test = _prepare_splits(train_df, test_df, config)
		model = train_fn(X_train, y_train, X_test, y_test, config.tabnet_config)
		folds.append(FoldResult(subject_id=subject_id, metrics={}, model=model))

	return folds


def _prepare_splits(
	train_df: pd.DataFrame,
	test_df: pd.DataFrame,
	config: TrainingConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
	X_train = train_df[config.feature_columns].to_numpy(dtype=float)
	y_train = train_df[config.label_column].to_numpy(dtype=int)
	X_test = test_df[config.feature_columns].to_numpy(dtype=float)
	y_test = test_df[config.label_column].to_numpy(dtype=int)

	X_train, X_test = _zscore_by_train(X_train, X_test)
	return X_train, y_train, X_test, y_test


def _zscore_by_train(
	X_train: np.ndarray, X_test: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
	mean = X_train.mean(axis=0)
	std = X_train.std(axis=0)
	std[std == 0] = 1.0
	return (X_train - mean) / std, (X_test - mean) / std


def _default_train_fn(
	X_train: np.ndarray,
	y_train: np.ndarray,
	X_test: np.ndarray,
	y_test: np.ndarray,
	config: TabNetConfig,
) -> Any:
	"""Placeholder training function that builds a TabNet model."""
	model = build_tabnet_classifier(config)
	_ = (X_train, y_train, X_test, y_test)
	return model
