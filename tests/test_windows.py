"""End-to-end window validation on a synthetic dual session with known truth.

The session mimics real recordings: H10 notifications at ~1 Hz carrying the
RR intervals since the last one, variable-size PPG frames stamped with their
last sample, a constant pulse transit delay, host zero points, and a burst of
arm motion in the Sense accelerometer.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from polar_ble_sdk.metrics.hrv import calculate_rmssd
from polar_ble_sdk.research.windows import build_windows

BASE_NS = 1_790_000_000 * 10**9
DURATION_S = 185.0
MOTION_S = (125.0, 185.0)


def _write_session(root: Path) -> list[float]:
    rng = np.random.default_rng(7)
    rr: list[float] = []
    t = 0.0
    while t < DURATION_S:
        v = 900 + 40 * np.sin(2 * np.pi * len(rr) / 5) + rng.normal(0, 8)
        rr.append(float(v))
        t += v / 1000
    beats = np.cumsum(rr) / 1000.0

    # H10 hr.csv: one notification per second with the RRs since the last one
    h10 = root / "h10" / "raw"
    h10.mkdir(parents=True)
    rows, first_notif, k = ["Timestamp_s,HeartRate_BPM,RR_Intervals_ms"], None, 0
    for sec in range(1, int(DURATION_S) + 1):
        batch = []
        while k < len(beats) and beats[k] <= sec - 0.3:  # notifies 0.3+ s later
            batch.append(rr[k])
            k += 1
        if batch:
            first_notif = sec if first_notif is None else first_notif
            rows.append(
                f"{sec - first_notif:.3f},66,{';'.join(f'{v:.1f}' for v in batch)}"
            )
    (h10 / "hr.csv").write_text("\n".join(rows), encoding="utf-8")

    # Sense ppg.csv: 135 Hz, 31-52 sample frames, pulse 0.25 s after each beat
    fs = 135.0
    ts = np.arange(0, DURATION_S, 1 / fs)
    pulse = np.zeros_like(ts)
    for b in beats + 0.25:
        pulse += np.exp(-0.5 * ((ts - b) / 0.08) ** 2)
    ch = (-500000 + 20000 * pulse).astype(int)  # same polarity as real Sense data
    sense = root / "sense" / "raw"
    sense.mkdir(parents=True)
    rows, i, first_last = ["Timestamp_s,Sample_Channels"], 0, None
    while i < len(ts):
        n = int(rng.integers(31, 53))
        frame = range(i, min(i + n, len(ts)))
        last = ts[frame[-1]]
        first_last = last if first_last is None else first_last
        cells = ",".join(f'"[{ch[j]}, {ch[j]}, {ch[j]}, 7]"' for j in frame)
        rows.append(f"{last - first_last:.6f},{cells}")
        i += n
    (sense / "ppg.csv").write_text("\n".join(rows), encoding="utf-8")

    # Sense acc.csv: still, then arm movement
    ta = np.arange(0, DURATION_S, 1 / 52)
    moving = (ta >= MOTION_S[0]) & (ta < MOTION_S[1])
    z = 1000 + np.where(moving, 300 * np.sin(2 * np.pi * 0.8 * ta), 0)
    acc = ["Timestamp_s,X_mG,Y_mG,Z_mG"] + [
        f"{a:.4f},0,0,{v:.1f}" for a, v in zip(ta, z, strict=True)
    ]
    (sense / "acc.csv").write_text("\n".join(acc), encoding="utf-8")

    meta = {
        "clock_zero_points": {
            "h10_hr_host_epoch_ns": BASE_NS + int(first_notif * 1e9),
            "sense_ppg_host_epoch_ns": BASE_NS + int(first_last * 1e9),
            "sense_acc_host_epoch_ns": BASE_NS,
        }
    }
    (root / "session_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return rr


def test_windows_recover_truth_and_flag_motion(tmp_path: Path) -> None:
    rr = _write_session(tmp_path)
    w = build_windows(tmp_path, window_s=60)
    assert len(w) == 3
    assert w["ref_ok"].all()

    true_hr = 60000 / np.mean(rr)
    rest = w[~w["artifact"]]
    assert len(rest) == 2
    assert rest["ref_hr"].to_numpy() == pytest.approx(true_hr, abs=1.5)
    # PPG beats vs reference: same beats, shifted by a constant transit delay
    assert (rest["ppg_hr"] - rest["ref_hr"]).abs().max() < 0.5
    ratio = rest["ppg_rmssd"] / rest["ref_rmssd"]
    assert ratio.to_numpy() == pytest.approx(1.0, abs=0.1)
    assert rest["ref_rmssd"].to_numpy() == pytest.approx(calculate_rmssd(rr), rel=0.25)

    moving = w[w["artifact"]]
    assert len(moving) == 1
    assert "motion" in moving["artifact_reason"].iloc[0]
