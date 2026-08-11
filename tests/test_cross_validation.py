"""Unit tests for the cross-validation metric functions in analysis/run_analysis.py."""

import os
import sys

import numpy as np
import pandas as pd
import pytest

# Make analysis/ importable (conftest adds src/ for the SDK; add analysis/ too)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))

import run_analysis as ra  # noqa: E402

# ---------------------------------------------------------------------------
# Lin's CCC
# ---------------------------------------------------------------------------


class TestLinsCcc:
    def test_perfect_agreement_is_one(self):
        x = np.array([60.0, 70.0, 80.0, 90.0, 100.0])
        assert ra.calculate_lins_ccc(x, x) == pytest.approx(1.0)

    def test_constant_bias_reduces_ccc_below_one(self):
        x = np.array([60.0, 70.0, 80.0, 90.0, 100.0])
        y = x + 5.0
        ccc = ra.calculate_lins_ccc(x, y)
        assert ccc < 1.0
        # Perfect correlation + constant offset: CCC = 2*var_x / (2*var_x + 25)
        expected = 2 * np.var(x, ddof=1) / (2 * np.var(x, ddof=1) + 25.0)
        assert ccc == pytest.approx(expected)

    def test_negative_correlation_gives_negative_ccc(self):
        x = np.array([60.0, 70.0, 80.0, 90.0, 100.0])
        y = -x
        assert ra.calculate_lins_ccc(x, y) < 0

    def test_too_few_points_returns_nan(self):
        assert np.isnan(ra.calculate_lins_ccc(np.array([60.0]), np.array([61.0])))


# ---------------------------------------------------------------------------
# ICC(2,1)
# ---------------------------------------------------------------------------


class TestIcc21:
    def test_perfect_agreement_is_one(self):
        x = np.array([60.0, 70.0, 80.0, 90.0, 100.0])
        assert ra.calculate_icc_2_1(x, x) == pytest.approx(1.0, abs=1e-6)

    def test_bounded_between_minus_one_and_one(self):
        rng = np.random.default_rng(0)
        x = rng.normal(80, 10, 50)
        y = rng.normal(80, 10, 50)
        icc = ra.calculate_icc_2_1(x, y)
        assert -1.0 <= icc <= 1.0

    def test_constant_offset_lowers_icc(self):
        x = np.array([60.0, 70.0, 80.0, 90.0, 100.0])
        icc_same = ra.calculate_icc_2_1(x, x)
        icc_offset = ra.calculate_icc_2_1(x, x + 10.0)
        assert icc_offset < icc_same

    def test_too_few_points_returns_nan(self):
        assert np.isnan(
            ra.calculate_icc_2_1(np.array([1.0, 2.0]), np.array([1.0, 2.0]))
        )


# ---------------------------------------------------------------------------
# Epoch binning
# ---------------------------------------------------------------------------


class TestBuildEpochs:
    def _make_df(self, n_seconds=30, gap_end=8):
        """Rows for both devices every second; Sense HR=0 during [0, gap_end).

        With gap_end=8, the first 10-s epoch (seconds 0-9) has 2 valid Sense
        samples (seconds 8, 9); later epochs have 10.
        """
        ts = pd.date_range("2026-08-07 15:22:00", periods=n_seconds, freq="1s")
        h10 = pd.DataFrame(
            {
                "Timestamp": ts,
                "H10_HR": np.full(n_seconds, 80.0),
                "H10_RMSSD": np.full(n_seconds, 40.0),
            }
        )
        sense = pd.DataFrame(
            {
                "Timestamp": ts,
                "Sense_HR": np.where(np.arange(n_seconds) < gap_end, 0.0, 85.0),
                "Sense_RMSSD": np.full(n_seconds, 50.0),
            }
        )
        merged = pd.merge(h10, sense, on="Timestamp", how="outer")
        merged["H10_ACC_Mag"] = 1000.0
        merged["Sense_ACC_Mag"] = 900.0
        return merged

    def test_epoch_binning_counts_samples(self):
        df = self._make_df(n_seconds=30)
        df = ra.flag_valid_hr(df)
        epochs = ra.build_epochs(df)
        assert len(epochs) == 3  # 30s / 10s epochs
        assert (epochs["h10_n"] == 10).all()
        # Sense has 2 valid samples in the first epoch (seconds 8,9), then 10
        assert epochs.iloc[0]["sense_n"] == 2
        assert epochs.iloc[1]["sense_n"] == 10
        assert epochs.iloc[2]["sense_n"] == 10

    def test_epoch_mean_excludes_zeros(self):
        df = self._make_df(n_seconds=30)
        df = ra.flag_valid_hr(df)
        epochs = ra.build_epochs(df)
        # First epoch has too few valid Sense samples (<5) -> HR forced NaN
        assert np.isnan(epochs.iloc[0]["sense_hr"])
        assert np.isnan(epochs.iloc[0]["h10_hr"])
        # Later epochs: sense HR mean excludes zeros -> 85.0, h10 -> 80.0
        assert epochs.iloc[1]["sense_hr"] == pytest.approx(85.0)
        assert epochs.iloc[1]["h10_hr"] == pytest.approx(80.0)

    def test_epoch_paired_valid_requires_min_samples(self):
        df = self._make_df(n_seconds=30)
        df = ra.flag_valid_hr(df)
        epochs = ra.build_epochs(df)
        # First epoch has sense_n=2 which is below MIN_EPOCH_SAMPLES=5
        assert not epochs.iloc[0]["hr_paired_valid"]
        assert epochs.iloc[1]["hr_paired_valid"]
        assert epochs.iloc[2]["hr_paired_valid"]

    def test_epoch_with_insufficient_sense_data_is_invalid(self):
        df = self._make_df(n_seconds=30, gap_end=9)  # sense valid from second 9
        df = ra.flag_valid_hr(df)
        epochs = ra.build_epochs(df)
        # First epoch: only 1 valid sense sample -> not paired-valid, HR forced NaN
        assert not epochs.iloc[0]["hr_paired_valid"]
        assert np.isnan(epochs.iloc[0]["sense_hr"])


# ---------------------------------------------------------------------------
# Bootstrap CIs
# ---------------------------------------------------------------------------


class TestBootstrapCi:
    def test_returns_bounds_in_order(self):
        rng = np.random.default_rng(1)
        data = rng.normal(0, 1, 100)
        lo, hi = ra.bootstrap_ci(data, np.mean, n_boot=500, seed=42)
        assert lo <= hi
        assert lo < 0 < hi  # mean ~0, CI straddles 0

    def test_too_few_points_returns_nan(self):
        lo, hi = ra.bootstrap_ci(np.array([1.0]), np.mean)
        assert np.isnan(lo) and np.isnan(hi)


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------


class TestGrading:
    def test_mae_grade(self):
        assert ra.grade_metrics({"mae": 3.0})["mae_grade"] == "valid"
        assert ra.grade_metrics({"mae": 6.0})["mae_grade"] == "poor"

    def test_mape_three_tiers(self):
        assert ra.grade_metrics({"mape": 4.0})["mape_grade"] == "valid"
        assert ra.grade_metrics({"mape": 7.0})["mape_grade"] == "acceptable"
        assert ra.grade_metrics({"mape": 12.0})["mape_grade"] == "poor"

    def test_bias_within_2bpm(self):
        assert ra.grade_metrics({"bias": 1.5})["bias_grade"] == "valid"
        assert ra.grade_metrics({"bias": -2.5})["bias_grade"] == "poor"

    def test_agreement_grades(self):
        g = ra.grade_metrics({"lins_ccc": 0.95, "icc_2_1": 0.8, "pearson_r": 0.95})
        assert g["ccc_grade"] == "valid"
        assert g["icc_grade"] == "valid"
        assert g["r_grade"] == "valid"

        g2 = ra.grade_metrics({"lins_ccc": 0.5, "icc_2_1": 0.5, "pearson_r": 0.5})
        assert g2["ccc_grade"] == "poor"
        assert g2["icc_grade"] == "poor"
        assert g2["r_grade"] == "poor"

    def test_nan_grades_are_na(self):
        g = ra.grade_metrics(
            {
                "mae": float("nan"),
                "mape": float("nan"),
                "bias": float("nan"),
                "lins_ccc": float("nan"),
                "icc_2_1": float("nan"),
                "pearson_r": float("nan"),
                "cv_sense": float("nan"),
                "dropout_rate": float("nan"),
            }
        )
        for key in (
            "mae_grade",
            "mape_grade",
            "bias_grade",
            "ccc_grade",
            "icc_grade",
            "r_grade",
            "cv_grade",
            "dropout_grade",
        ):
            assert g[key] == "n/a"


# ---------------------------------------------------------------------------
# compute_metrics on synthetic data
# ---------------------------------------------------------------------------


class TestComputeMetrics:
    def _make_epoch_frame(self, n_epochs=20):
        """Paired 10-s epoch rows with a small device offset."""
        h10 = np.linspace(80, 100, n_epochs)
        sense = h10 + 2.0 + np.random.default_rng(7).normal(0, 1, n_epochs)
        return pd.DataFrame(
            {
                "epoch_start": pd.date_range(
                    "2026-08-07 15:22:00", periods=n_epochs, freq="10s"
                ),
                "h10_hr": h10,
                "sense_hr": sense,
                "h10_rmssd": np.full(n_epochs, 40.0),
                "sense_rmssd": np.full(n_epochs, 50.0),
                "h10_n": np.full(n_epochs, 10),
                "sense_n": np.full(n_epochs, 10),
                "hr_paired_valid": np.ones(n_epochs, dtype=bool),
                "hr_diff": sense - h10,
                "hr_abs_err": np.abs(sense - h10),
            }
        )

    def test_synthetic_epoch_frame_produces_sane_metrics(self):
        ep = self._make_epoch_frame()
        # compute_metrics expects a 1-s row frame; feed epochs through directly
        # is not the intended path, so instead exercise the stat helpers.
        x = ep["h10_hr"].to_numpy()
        y = ep["sense_hr"].to_numpy()
        diff = y - x
        mae = np.mean(np.abs(diff))
        bias = np.mean(diff)
        assert ra.calculate_lins_ccc(x, y) > 0.9  # tight offset -> high CCC
        assert ra.calculate_icc_2_1(x, y) > 0.5  # random offset reduces ICC
        assert 1.0 < mae < 4.0
        assert 1.0 < bias < 4.0
