"""Unit tests for the Sense HR artifact detector in analysis/run_analysis.py."""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))

import run_analysis as ra  # noqa: E402


def make_second_frame(seconds=120, h10_hr=75.0, sense_hr=75.0, seed=0):
    """Build a 1-s row frame with constant H10/Sense HR by default."""
    ts = pd.date_range("2026-08-12 10:00:00", periods=seconds, freq="1s")
    return pd.DataFrame(
        {
            "Timestamp": ts,
            "H10_HR": h10_hr if np.isscalar(h10_hr) else h10_hr,
            "Sense_HR": sense_hr if np.isscalar(sense_hr) else sense_hr,
            "H10_RMSSD": 40.0,
            "Sense_RMSSD": 120.0,
            "H10_ACC_Mag": 1000.0,
            "Sense_ACC_Mag": 1000.0,
        }
    )


class TestDetectSenseArtifacts:
    def test_clean_data_no_artifacts(self):
        # Slight jitter in both, no plateau, no diff
        rng = np.random.default_rng(1)
        n = 120
        df = make_second_frame(n)
        df["H10_HR"] = 75 + rng.normal(0, 0.5, n).round(0)
        df["Sense_HR"] = df["H10_HR"] + rng.normal(-2, 0.5, n).round(0)
        out = ra.detect_sense_artifacts(df)
        assert out["artifact"].sum() == 0

    def test_plateau_exact_constant_detected(self):
        # Sense exactly 37 for 30 s while H10 moves 80->90: classic lock.
        # 37 is far from H10 median (~85) -> plateau layer flags it.
        n = 120
        df = make_second_frame(n)
        df["H10_HR"] = np.where(np.arange(n) < 60, 80.0, 90.0)
        df["Sense_HR"] = 75.0
        # inject a 30-s exact plateau at t=45..74
        df.loc[45:74, "Sense_HR"] = 37.0
        out = ra.detect_sense_artifacts(df)
        flagged = sorted(np.where(out["artifact"])[0].tolist())
        assert len(flagged) >= 28  # most of the plateau
        assert 45 in flagged and 74 in flagged
        assert (out.loc[flagged, "artifact_layer"] == "plateau").all()

    def test_plateau_requires_value_far_from_h10(self):
        # Sense constant 68 for 30 s, H10 ~73 (genuine rest): plateau value
        # is within diff bounds -> NOT an artifact.
        n = 120
        df = make_second_frame(n)
        df["H10_HR"] = 73.0
        df["Sense_HR"] = 73.0
        df.loc[45:74, "Sense_HR"] = 68.0  # exact 30 s, but |68-73|=5 within bounds
        out = ra.detect_sense_artifacts(df)
        assert out["artifact"].sum() == 0

    def test_plateau_excludes_zero_hr(self):
        # Sense HR=0 for 30 s (warmup) while H10 moves: that's dropout, not artifact
        n = 120
        df = make_second_frame(n)
        df["H10_HR"] = np.where(np.arange(n) < 60, 80.0, 90.0)
        df.loc[45:74, "Sense_HR"] = 0.0
        out = ra.detect_sense_artifacts(df)
        assert out["artifact"].sum() == 0

    def test_short_plateau_not_detected_when_no_diff(self):
        # 10-s exact plateau < 20s threshold AND within diff bounds -> no flag.
        n = 120
        df = make_second_frame(n)
        df["H10_HR"] = 80.0
        df["Sense_HR"] = 75.0
        df.loc[45:54, "Sense_HR"] = 78.0  # 10 s exact but |78-80|=2, within bounds
        out = ra.detect_sense_artifacts(df)
        assert out["artifact"].sum() == 0

    def test_sustained_diff_detected(self):
        # Sense 35 below H10 for 30 s -> diff layer
        n = 120
        df = make_second_frame(n)
        df.loc[30:59, "Sense_HR"] = 40.0  # H10=75, diff=-35
        out = ra.detect_sense_artifacts(df)
        flagged = sorted(np.where(out["artifact"])[0].tolist())
        assert 30 in flagged and 59 in flagged
        assert (out.loc[flagged, "artifact_layer"] == "diff").all()

    def test_transient_diff_not_detected(self):
        # 2-s spike of -35 -> not sustained, no flag
        n = 120
        df = make_second_frame(n)
        df.loc[30:31, "Sense_HR"] = 40.0
        out = ra.detect_sense_artifacts(df)
        assert out["artifact"].sum() == 0

    def test_artifact_seconds_excluded_from_epochs(self):
        # Inject a long diff artifact; the epoch containing it must lose paired validity
        n = 120
        df = make_second_frame(n)
        df.loc[30:89, "Sense_HR"] = 40.0  # 60 s artifact (rows 30-89)
        df = ra.detect_sense_artifacts(df)
        epochs = ra.build_epochs(df)

        # Find the epoch containing t=30 (row 30) and t=90 (row 90)
        def epoch_of(seconds_into_session):
            ts = df["Timestamp"].iloc[seconds_into_session]
            return epochs[epochs["epoch_start"] <= ts].iloc[-1]

        ep_artifact = epoch_of(30)
        assert not ep_artifact["hr_paired_valid"]  # artifact seconds excluded
        ep_clean = epoch_of(0)  # t=0, before the artifact
        assert ep_clean["hr_paired_valid"]
        ep_clean2 = epoch_of(110)  # after the artifact
        assert ep_clean2["hr_paired_valid"]


class TestArtifactMetrics:
    def test_artifact_rate_reported_and_metrics_exclude(self):
        n = 120
        df = make_second_frame(n)
        df.loc[30:89, "Sense_HR"] = 40.0  # 60 s artifact
        m = ra.compute_metrics(df)
        assert m["n_artifact_seconds"] >= 58
        assert m["artifact_rate"] >= 48.0  # ~50% of 120s
        # 12 epochs total; epochs 3-8 fully flagged -> ~6 survive
        assert m["n_epochs"] <= 6

    def test_clean_session_artifact_rate_zero(self):
        rng = np.random.default_rng(2)
        n = 120
        df = make_second_frame(n)
        df["H10_HR"] = 75 + rng.normal(0, 0.5, n).round(0)
        df["Sense_HR"] = df["H10_HR"] + rng.normal(-2, 0.5, n).round(0)
        m = ra.compute_metrics(df)
        assert m["artifact_rate"] == 0.0
        assert m["artifact_runs"] == []
