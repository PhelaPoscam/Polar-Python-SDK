"""Feature engineering for Jui et al. (2026) Table 2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class WindowSpec:
	window_seconds: float = 25.0
	overlap_ratio: float = 0.5

	@property
	def step_seconds(self) -> float:
		return self.window_seconds * (1.0 - self.overlap_ratio)


def generate_feature_matrix(
	df: pd.DataFrame,
	time_col: str,
	eda_col: str,
	hr_col: str,
	window_spec: WindowSpec | None = None,
) -> pd.DataFrame:
	"""Extract 21 features per window for EDA and HR plus covariance."""
	spec = window_spec or WindowSpec()
	if time_col not in df.columns:
		raise ValueError(f"Missing time column: {time_col}")

	df = df.copy()
	df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
	df = df.dropna(subset=[time_col, eda_col, hr_col]).sort_values(time_col)
	if df.empty:
		return pd.DataFrame()

	start_time = df[time_col].iloc[0]
	end_time = df[time_col].iloc[-1]
	step = pd.to_timedelta(spec.step_seconds, unit="s")
	window = pd.to_timedelta(spec.window_seconds, unit="s")

	rows: list[dict[str, float]] = []
	current = start_time
	while current + window <= end_time:
		window_df = df[(df[time_col] >= current) & (df[time_col] < current + window)]
		if not window_df.empty:
			rows.append(
				_compute_window_features(
					window_df,
					eda_col=eda_col,
					hr_col=hr_col,
					window_start=current,
					window_end=current + window,
				)
			)
		current += step

	return pd.DataFrame(rows)


def _compute_window_features(
	window_df: pd.DataFrame,
	eda_col: str,
	hr_col: str,
	window_start: pd.Timestamp,
	window_end: pd.Timestamp,
) -> dict[str, float]:
	eda_stats = _basic_stats(window_df[eda_col])
	hr_stats = _basic_stats(window_df[hr_col])
	covariance = float(np.cov(window_df[eda_col], window_df[hr_col])[0, 1])

	features: dict[str, float] = {
		"window_start": window_start.timestamp(),
		"window_end": window_end.timestamp(),
		"eda_cov_hr": covariance,
	}
	for key, value in eda_stats.items():
		features[f"eda_{key}"] = value
	for key, value in hr_stats.items():
		features[f"hr_{key}"] = value
	return features


def _basic_stats(series: Iterable[float]) -> dict[str, float]:
	values = pd.Series(series).astype(float)
	return {
		"mean": float(values.mean()),
		"median": float(values.median()),
		"std": float(values.std(ddof=0)),
		"var": float(values.var(ddof=0)),
		"min": float(values.min()),
		"max": float(values.max()),
		"skew": float(values.skew()),
		"kurtosis": float(values.kurtosis()),
		"range": float(values.max() - values.min()),
	}
