"""Explainability utilities (SHAP/LIME) for TabNet."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def explain_global_shap(model: Any, X: pd.DataFrame, feature_names: list[str]) -> dict[str, float]:
	"""Compute global feature importance using SHAP if available."""
	try:
		import shap
	except ImportError as exc:  # pragma: no cover - optional dependency
		raise ImportError("shap is required for SHAP explanations") from exc

	explainer = shap.Explainer(model.predict, X)
	shap_values = explainer(X)
	mean_abs = np.abs(shap_values.values).mean(axis=0)
	return dict(zip(feature_names, mean_abs))


def explain_local_lime(
	model: Any,
	X_row: pd.Series,
	feature_names: list[str],
	class_names: list[str] | None = None,
) -> dict[str, float]:
	"""Explain a single prediction using LIME if available."""
	try:
		from lime.lime_tabular import LimeTabularExplainer
	except ImportError as exc:  # pragma: no cover - optional dependency
		raise ImportError("lime is required for LIME explanations") from exc

	class_names = class_names or ["no_stress", "stress"]
	explainer = LimeTabularExplainer(
		training_data=np.array([X_row.to_numpy(dtype=float)]),
		feature_names=feature_names,
		class_names=class_names,
		mode="classification",
	)
	explanation = explainer.explain_instance(
		X_row.to_numpy(dtype=float),
		model.predict_proba,
		num_features=len(feature_names),
	)
	return dict(explanation.as_list())
