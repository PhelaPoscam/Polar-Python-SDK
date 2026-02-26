"""Scaffold tests for advanced models."""

from __future__ import annotations

import importlib.util

import pandas as pd
import pytest

from awe_polar.advanced_models import explainability, features, tabnet_model, tabnet_trainer


def test_generate_feature_matrix_basic() -> None:
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=6, freq="5s"),
            "eda": [1.0, 1.1, 1.2, 1.3, 1.4, 1.5],
            "hr": [60, 62, 61, 63, 64, 65],
        }
    )
    result = features.generate_feature_matrix(
        df,
        time_col="timestamp",
        eda_col="eda",
        hr_col="hr",
        window_spec=features.WindowSpec(window_seconds=25, overlap_ratio=0.5),
    )
    assert not result.empty
    assert "eda_mean" in result.columns
    assert "hr_mean" in result.columns
    assert "eda_cov_hr" in result.columns


def test_tabnet_model_optional_dependency() -> None:
    config = tabnet_model.default_tabnet_config()
    if tabnet_model.TabNetClassifier is None:
        with pytest.raises(ImportError):
            tabnet_model.build_tabnet_classifier(config)
    else:
        model = tabnet_model.build_tabnet_classifier(config)
        assert model is not None


def test_explainability_optional_dependencies() -> None:
    if importlib.util.find_spec("shap") is None:
        with pytest.raises(ImportError):
            explainability.explain_global_shap(None, pd.DataFrame(), [])
    if importlib.util.find_spec("lime") is None:
        with pytest.raises(ImportError):
            explainability.explain_local_lime(None, pd.Series(dtype=float), [])


def test_loso_training_scaffold() -> None:
    df = pd.DataFrame(
        {
            "subject": ["1", "1", "2", "2"],
            "feature_a": [0.1, 0.2, 0.3, 0.4],
            "feature_b": [1.0, 0.9, 0.8, 0.7],
            "label": [0, 1, 0, 1],
        }
    )
    config = tabnet_trainer.TrainingConfig(
        feature_columns=["feature_a", "feature_b"],
        label_column="label",
        subject_column="subject",
    )

    def train_stub(X_train, y_train, X_test, y_test, tabnet_config):
        _ = (X_train, y_train, X_test, y_test, tabnet_config)
        return {"trained": True}

    results = tabnet_trainer.run_loso_training(df, config, train_fn=train_stub)
    assert len(results) == 2
    assert all(result.model for result in results)
