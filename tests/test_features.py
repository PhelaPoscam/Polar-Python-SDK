"""Feature extraction on synthetic ECG and RR series with known content."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

nk = pytest.importorskip("neurokit2")

from polar_ble_sdk.research.features import (  # noqa: E402
    delineate_segment,
    extract_features,
    hrv_long,
    load_signals,
)

FS = 130


def _ecg(duration: int, seed: int = 1, fs: int = FS) -> np.ndarray:
    return 1000 * nk.ecg_simulate(
        duration=duration, sampling_rate=fs, heart_rate=70, random_state=seed
    )


def test_delineation_at_h10_rate_matches_500_hz() -> None:
    """130 Hz intervals stay within two samples of a 500 Hz delineation."""
    _, h10 = delineate_segment(_ecg(60), FS)
    _, ref = delineate_segment(_ecg(60, fs=500), 500)
    assert len(h10) > 60
    assert h10["complete"].mean() > 0.8
    assert h10["r_amp"].median() > 0
    for col in ("qrs_dur", "pr", "qt", "qtc_bazett", "qtc_fridericia"):
        assert abs(h10[col].median() - ref[col].median()) <= 2 * 1000 / FS, col


@pytest.mark.parametrize("f_hz, lf_dominant", [(0.1, True), (0.25, False)])
def test_lf_hf_band(f_hz: float, lf_dominant: bool) -> None:
    rng = np.random.default_rng(0)
    rr, t = [], 0.0
    while t < 300:
        v = 900 + 50 * np.sin(2 * np.pi * f_hz * t) + rng.normal(0, 3)
        rr.append(float(v))
        t += v / 1000
    out = hrv_long(np.cumsum(rr) / 1000, rr)
    assert (out["lf_hf_5m"] > 1) == lf_dominant
    assert 0 < out["dfa_a1_5m"] < 2


def test_single_session_gap_split(tmp_path: Path) -> None:
    """A 5 s hole in the ECG splits it: no interval spans the gap."""
    x = np.concatenate([_ecg(65, 1), _ecg(65, 2)])
    t = np.arange(len(x)) / FS
    t[len(x) // 2 :] += 5.0
    raw = tmp_path / "raw"
    raw.mkdir()
    lines = ["Timestamp_s,uV_Samples"]
    for i in range(0, len(x), 73):
        frame = x[i : i + 73].astype(int)
        lines.append(f"{t[i + len(frame) - 1]:.3f}," + ",".join(map(str, frame)))
    (raw / "ecg.csv").write_text("\n".join(lines), encoding="utf-8")
    meta = {
        "devices": {"h10": {}},
        "clock_zero_points": {"ecg_host_epoch_ns": 1_790_000_000 * 10**9},
    }
    (tmp_path / "session_meta.json").write_text(json.dumps(meta), encoding="utf-8")

    sig = load_signals(tmp_path)
    assert sig.ecg_beats["rr"].isna().sum() == 2  # first beat of each segment
    assert sig.ecg_beats["rr"].max() < 1500
    feats = extract_features(tmp_path, signals=sig)
    assert len(feats) == 2
    assert feats["ecg_qrs_dur"].notna().all()
    assert {"ecg_dwt_d3_rel_energy", "ecg_imf1_mean_freq_hz", "ecg_pca1_var"} <= set(
        feats
    )
