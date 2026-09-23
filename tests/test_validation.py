"""Unit tests for agreement statistics and the Markdown report."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from polar_ble_sdk.research.report import generate_markdown_report
from polar_ble_sdk.research.validation import (
    agreement,
    block_bootstrap_ci,
    calculate_icc_2_1,
    calculate_lins_ccc,
    calculate_wscv,
    grade,
    repeated_measures_agreement,
    validate_windows,
)


class TestCoefficients:
    def test_lins_ccc_perfect_agreement(self) -> None:
        x = np.array([60.0, 70.0, 80.0, 90.0])
        assert calculate_lins_ccc(x, x) == pytest.approx(1.0)

    def test_lins_ccc_penalises_offset(self) -> None:
        x = np.array([60.0, 70.0, 80.0, 90.0])
        assert calculate_lins_ccc(x, x + 5.0) < 1.0

    def test_icc_2_1(self) -> None:
        x = np.array([60.0, 70.0, 80.0, 90.0, 100.0])
        assert calculate_icc_2_1(x, x + np.array([1, -1, 1, -1, 0])) > 0.95

    def test_wscv_is_rms_and_zero_for_identity(self) -> None:
        x = np.array([60.0, 80.0])
        assert calculate_wscv(x, x) == 0.0
        y = np.array([66.0, 80.0])  # one pair differs
        cv = (6 / np.sqrt(2)) / 63.0
        assert calculate_wscv(x, y) == pytest.approx(np.sqrt(cv**2 / 2) * 100)


class TestAgreement:
    def test_constant_offset(self) -> None:
        rng = np.random.default_rng(1)
        x = rng.uniform(55, 100, 200)
        y = x + 2.0 + rng.normal(0, 1.0, 200)
        a = agreement(x, y, n_boot=200)
        assert a["bias"] == pytest.approx(2.0, abs=0.3)
        assert a["bias_ci_low"] < a["bias"] < a["bias_ci_high"]
        assert a["loa_upper"] - a["loa_lower"] == pytest.approx(2 * 1.96, rel=0.2)
        assert a["loa_upper_ci_low"] < a["loa_upper"] < a["loa_upper_ci_high"]
        assert a["prop_bias_p"] > 0.01

    def test_proportional_bias_is_detected(self) -> None:
        x = np.linspace(50, 150, 50)
        a = agreement(x, 1.2 * x, n_boot=100)
        assert a["prop_bias_slope"] > 0
        assert a["prop_bias_p"] < 0.001

    def test_log_ratio_limits_for_rmssd(self) -> None:
        rng = np.random.default_rng(2)
        x = rng.uniform(20, 80, 100)
        y = x * 1.1 * np.exp(rng.normal(0, 0.05, 100))
        a = agreement(x, y, log_ratio=True, n_boot=100)
        assert a["bias"] == pytest.approx(1.1, abs=0.02)
        assert a["loa_lower"] < 1.1 < a["loa_upper"]

    def test_block_bootstrap_is_reproducible(self) -> None:
        x = np.arange(30, dtype=float)
        y = x + np.sin(x)
        stat = lambda a, b: float(np.mean(b - a))  # noqa: E731
        assert block_bootstrap_ci(x, y, stat, n_boot=200) == block_bootstrap_ci(
            x, y, stat, n_boot=200
        )


class TestRepeatedMeasures:
    def test_between_subject_variance_is_counted(self) -> None:
        # No within-subject spread: SD must equal the SD of subject mean diffs
        df = pd.DataFrame(
            {
                "p": ["a"] * 3 + ["b"] * 3,
                "ref": [60.0] * 6,
                "test": [61.0] * 3 + [63.0] * 3,
            }
        )
        r = repeated_measures_agreement(df, "p", "ref", "test", n_boot=100)
        assert r["bias"] == pytest.approx(2.0)
        assert r["sd_diff"] == pytest.approx(np.std([1.0, 3.0], ddof=1))

    def test_needs_two_participants(self) -> None:
        df = pd.DataFrame({"p": ["a"] * 4, "ref": [60.0] * 4, "test": [61.0] * 4})
        assert "bias" not in repeated_measures_agreement(df, "p", "ref", "test")


def test_grades_follow_cited_bands() -> None:
    g = grade({"mape": 8.0, "lins_ccc": 0.96, "icc_2_1": 0.8})
    assert g == {"mape": "acceptable", "lins_ccc": "substantial", "icc_2_1": "good"}


def _windows() -> pd.DataFrame:
    ref = np.array([60.0, 62, 65, 70, 72, 68, 64, 90, 95])
    ppg = ref + np.array([0.2, -0.1, 0.3, 0.0, -0.2, 0.1, 0.2, -40, -45])
    return pd.DataFrame(
        {
            "start": pd.date_range("2026-01-01", periods=len(ref), freq="60s"),
            "ref_hr": ref,
            "ppg_hr": ppg,
            "ref_rmssd": ref * 0.6,
            "ppg_rmssd": ref * 0.61,
            "ref_ok": True,
            "artifact": [False] * 7 + [True, True],
            "artifact_reason": [""] * 7 + ["motion", "motion"],
        }
    )


def test_primary_result_keeps_artifact_windows() -> None:
    results = {r["label"]: r for r in validate_windows(_windows(), n_boot=100)}
    hr = results["PPG HR (beats)"]
    assert hr["all"]["n"] == 9  # primary: everything with a valid reference
    assert hr["clean"]["n"] == 7
    assert hr["all"]["mae"] > 5 > hr["clean"]["mae"]
    assert results["PPG RMSSD"]["all"]["log_ratio"]


def test_markdown_report_has_primary_and_sensitivity() -> None:
    w = _windows()
    md = generate_markdown_report(validate_windows(w, n_boot=100), "s1", w, 60)
    assert "Primary: all windows" in md
    assert "Sensitivity: artifact windows excluded" in md
    assert "PPG HR (beats)" in md
