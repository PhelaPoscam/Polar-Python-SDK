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

    def test_sustained_diff_is_flagged_only_when_long_enough(self) -> None:
        # 20 s of >15 BPM disagreement, then 5 s of it: only the first run counts.
        h10 = [70.0] * 50
        sense = [100.0] * 20 + [70.0] * 25 + [100.0] * 5
        df = pd.DataFrame({"H10_HR": h10, "Sense_HR": sense})
        res = detect_sense_artifacts(df, min_plateau_sec=100, min_diff_sec=15)
        assert list(res["artifact"])[:20] == [True] * 20
        assert not res["artifact"][20:].any()
        assert set(res.loc[res["artifact"], "artifact_layer"]) == {"diff"}

    def test_ppi_quality_runs_are_flagged(self) -> None:
        n = 40
        df = pd.DataFrame(
            {
                "H10_HR": [70.0 + i * 0.1 for i in range(n)],
                "Sense_HR": [70.0 + i * 0.1 for i in range(n)],
                "PPI_SkinContact": [1] * 10 + [0] * 20 + [1] * 10,
                "PPI_ErrEst_ms": [10] * n,
            }
        )
        res = detect_sense_artifacts(df, min_plateau_sec=100, min_contact_sec=15)
        assert res["artifact"].sum() == 20
        assert set(res.loc[res["artifact"], "artifact_layer"]) == {"ppi_quality"}

    def test_plateau_layer_wins_over_diff(self) -> None:
        """Plateaus are labelled last-writer-wins; diff only fills unlabelled rows."""
        h10 = [60.0 + i * 0.5 for i in range(30)]
        sense = [100.0] * 30  # constant and far from H10: both rules fire
        df = pd.DataFrame({"H10_HR": h10, "Sense_HR": sense})
        res = detect_sense_artifacts(df, min_plateau_sec=20, min_diff_sec=15)
        assert res["artifact"].all()
        assert set(res["artifact_layer"]) == {"plateau_sense"}

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

    def test_dropout_rate_decoupled_from_artifacts(self) -> None:
        """Verify that sensor motion artifacts do not inflate BLE transmission dropout rate."""
        ts = pd.date_range("2026-08-18 12:00:00", periods=50, freq="1s")
        # 50 total records, all 50 received (no BLE packet loss)
        # 25 seconds of flatline plateau in Sense
        h10 = [60.0 + i * 0.5 for i in range(50)]
        sense = [70.0] * 25 + [60.0 + i * 0.5 for i in range(25, 50)]
        df = pd.DataFrame({"Timestamp": ts, "H10_HR": h10, "Sense_HR": sense})
        metrics = compute_validation_metrics(df)

        assert metrics["dropout_rate"] == 0.0  # 0% transmission loss
        assert metrics["artifact_rate"] >= 40.0  # ~50% motion artifact rate

    def test_symmetric_plateau_detection(self) -> None:
        """Verify plateau artifacts are flagged symmetrically on either sensor."""
        # Plateau on H10 (reference sensor), varying Sense
        h10 = [70.0] * 25 + [80.0] * 5
        sense = [60.0 + i * 0.5 for i in range(30)]
        df = pd.DataFrame({"H10_HR": h10, "Sense_HR": sense})
        res = detect_sense_artifacts(df, min_plateau_sec=20)
        assert res["artifact"].sum() >= 20

    def test_generate_markdown_report_sdk_mode_notice(self) -> None:
        """Verify empty metrics dict produces clean SDK Mode Operating Notice without crashing."""
        md = generate_markdown_report({}, "sdk_session_001")
        assert "sdk_session_001" in md
        assert "Verity Sense SDK Mode Active" in md
