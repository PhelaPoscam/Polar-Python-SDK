"""Unit tests for research validation, metrics, and report generation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from polar_ble_sdk.research.report import generate_markdown_report
from polar_ble_sdk.research.validation import (
    bootstrap_ci,
    build_epochs,
    calculate_icc_2_1,
    calculate_lins_ccc,
    compute_validation_metrics,
    detect_sense_artifacts,
)


class TestValidationMetrics:
    def test_lins_ccc_perfect_agreement(self) -> None:
        x = [60.0, 70.0, 80.0, 90.0, 100.0]
        y = [60.0, 70.0, 80.0, 90.0, 100.0]
        ccc = calculate_lins_ccc(x, y)
        assert pytest.approx(ccc, 1e-4) == 1.0

    def test_lins_ccc_with_offset(self) -> None:
        x = [60.0, 70.0, 80.0, 90.0, 100.0]
        y = [65.0, 75.0, 85.0, 95.0, 105.0]
        ccc = calculate_lins_ccc(x, y)
        # Offset reduces concordance below 1.0 even if correlation is 1.0
        assert 0.8 < ccc < 1.0

    def test_icc_2_1_calculation(self) -> None:
        x = [60.0, 70.0, 80.0, 90.0, 100.0]
        y = [61.0, 69.0, 81.0, 89.0, 101.0]
        icc = calculate_icc_2_1(x, y)
        assert icc > 0.95

    def test_bootstrap_ci(self) -> None:
        data = [10.0, 12.0, 11.0, 13.0, 12.0, 14.0, 11.0, 12.0]
        lo, hi = bootstrap_ci(data, lambda s: float(np.mean(s)), n_boot=200, seed=42)
        assert lo < 12.0 < hi

    def test_detect_sense_artifacts(self) -> None:
        # Create 25 seconds of plateau
        h10 = [60.0 + i * 0.5 for i in range(30)]
        sense = [70.0] * 25 + [85.0] * 5
        df = pd.DataFrame({"H10_HR": h10, "Sense_HR": sense})
        res = detect_sense_artifacts(df, min_plateau_sec=20)
        assert res["artifact"].sum() >= 20

    def test_build_epochs(self) -> None:
        ts = pd.date_range("2026-08-18 12:00:00", periods=20, freq="1s")
        df = pd.DataFrame(
            {
                "Timestamp": ts,
                "H10_HR": [70.0] * 20,
                "Sense_HR": [71.0] * 20,
                "H10_RMSSD": [45.0] * 20,
                "Sense_RMSSD": [44.0] * 20,
                "artifact": [False] * 20,
            }
        )
        epochs = build_epochs(df, epoch_sec=10, min_samples=5)
        assert len(epochs) == 2
        assert epochs["hr_paired_valid"].all()

    def test_compute_validation_metrics_and_grading(self) -> None:
        ts = pd.date_range("2026-08-18 12:00:00", periods=60, freq="1s")
        df = pd.DataFrame(
            {
                "Timestamp": ts,
                "H10_HR": np.linspace(60, 80, 60),
                "Sense_HR": np.linspace(60.5, 80.5, 60),
                "H10_RMSSD": [40.0] * 60,
                "Sense_RMSSD": [41.0] * 60,
            }
        )
        metrics = compute_validation_metrics(df)
        assert metrics["mae"] == pytest.approx(0.5, 1e-2)
        assert metrics["bias"] == pytest.approx(0.5, 1e-2)
        assert metrics["mae_grade"] == "valid"

    def test_generate_markdown_report(self) -> None:
        metrics = {
            "mae": 1.2,
            "mape": 1.5,
            "bias": 0.3,
            "lins_ccc": 0.98,
            "icc_2_1": 0.97,
            "pearson_r": 0.99,
            "wscv": 1.2,
            "dropout_rate": 0.0,
            "mae_grade": "valid",
            "mape_grade": "valid",
            "bias_grade": "valid",
            "ccc_grade": "valid",
            "icc_grade": "valid",
            "r_grade": "valid",
            "cv_grade": "valid",
            "dropout_grade": "valid",
        }
        md = generate_markdown_report(metrics, "test_session_123")
        assert "test_session_123" in md
        assert "MAE" in md
