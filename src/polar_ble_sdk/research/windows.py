"""Windowed, beat-level cross-validation of the Verity Sense against H10 RR intervals.

Every stream is placed on one clock, host local time (the clock of the summary
CSVs and markers), using the per-stream host zero points in session_meta.json.
Device clocks cannot be used: the H10's is typically never set and the Sense's
may be minutes off. The recording is then cut into fixed, non-overlapping
windows (default 60 s).

- Reference: H10 RR intervals (ECG-derived on the device, 1/1024 s) from
  ``h10/raw/hr.csv``, cleaned with :func:`~polar_ble_sdk.metrics.hrv.rr_valid_mask`.
- Test methods: beats detected in raw PPG (``sense/raw/ppg.csv``) and, when
  recorded, the Sense's own PPI stream (``sense/raw/ppi.csv``).
- Artifacts: flagged from the Sense's own data only (accelerometer motion, PPG
  signal quality and coverage, skin contact), never from the reference, so
  excluding them cannot bias agreement towards the reference.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from polar_ble_sdk.metrics.hrv import calculate_rmssd, rr_valid_mask
from polar_ble_sdk.research.loader import _parse_wide_ppg_csv, host_zero
from polar_ble_sdk.research.ppg import (
    bandpass_filter,
    beat_intervals,
    estimate_fs,
    spectral_hr,
    spectral_sqi,
    split_segments,
)

WINDOW_S = 60
# Per-second SD of the Sense |acc|. Seated rest measured <= 5 mG, arm
# movement >= 50 mG (session 20260923_115103); 20 mG sits between them.
MOTION_SD_MG = 20.0
MOTION_MAX_FRAC = 0.10  # window is motion-affected if > 10 % of its seconds move
SQI_MIN = 0.30
MIN_COVERAGE = 0.80  # valid beats must span >= 80 % of the window
MIN_CONTACT_FRAC = 0.90
NOTIFICATION_GAP_S = 1.5  # H10 notifies at ~1 Hz; a longer gap lost beats
PPG_CHANNELS = ("ch1", "ch2", "ch3")  # ch4 is ambient light
_EMPTY_SERIES = pd.Series(dtype=float, index=pd.DatetimeIndex([]))


def _read_meta(session_dir: Path) -> dict[str, Any]:
    try:
        return json.loads((session_dir / "session_meta.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _to_host(anchor: pd.Timestamp, seconds: Any) -> pd.DatetimeIndex:
    return anchor + pd.to_timedelta(np.asarray(seconds, dtype=float), unit="s")


def load_h10_beats(session_dir: Path, meta: dict[str, Any]) -> pd.DataFrame:
    """H10 beats as ``t`` (host time of the beat ending the interval) and ``rr_ms``.

    ``rr_ms`` is NaN at a gap (lost notification): the next interval is not
    adjacent to the previous one. Relative beat times come from the cumulative
    RR sum, which is exact; the H10 notifies ~1 s after a beat, not at it, so
    each run between gaps is anchored with the smallest notification lag.
    """
    path = session_dir / "h10" / "raw" / "hr.csv"
    anchor = host_zero(meta, "h10_hr")
    if not path.exists() or anchor is None:
        return pd.DataFrame(columns=["t", "rr_ms"])
    raw = pd.read_csv(path, dtype={"RR_Intervals_ms": str})

    runs: list[tuple[list[float], list[float]]] = []  # (notif times, rr list) per run
    prev_t = None
    for t_s, rr_str in zip(raw["Timestamp_s"], raw["RR_Intervals_ms"], strict=True):
        rrs = [float(v) for v in str(rr_str).split(";") if v and v != "nan"]
        if prev_t is None or t_s - prev_t > NOTIFICATION_GAP_S:
            runs.append(([], []))
        prev_t = t_s
        for k, rr in enumerate(rrs):
            runs[-1][0].append(t_s if k == len(rrs) - 1 else np.nan)
            runs[-1][1].append(rr)

    times: list[float] = []
    rr_out: list[float] = []
    for notif, rrs in runs:
        if not rrs:
            continue
        cum = np.cumsum(rrs) / 1000.0
        notif_arr = np.asarray(notif)
        known = ~np.isnan(notif_arr)
        lag = float(np.min(notif_arr[known] - cum[known])) if known.any() else 0.0
        if times:
            # Gap marker: this run's first interval doesn't follow the last one.
            times.append(lag + cum[0] - rrs[0] / 1000.0)
            rr_out.append(np.nan)
        times.extend((lag + cum).tolist())
        rr_out.extend(rrs)
    return pd.DataFrame({"t": _to_host(anchor, times), "rr_ms": rr_out})


def load_ppg_channels(
    session_dir: Path, meta: dict[str, Any]
) -> tuple[dict[str, pd.DataFrame], dict[str, np.ndarray], pd.DatetimeIndex, float]:
    """PPG beats per channel (``t``, ``ibi_ms``) and the band-passed signals.

    Returns ``(beats by channel, filtered signal by channel, host sample times, fs)``.
    """
    path = session_dir / "sense" / "raw" / "ppg.csv"
    anchor = host_zero(meta, "sense_ppg")
    if not path.exists() or anchor is None:
        return {}, {}, pd.DatetimeIndex([]), float("nan")
    df = _parse_wide_ppg_csv(path).sort_values("Timestamp_s")
    t = df["Timestamp_s"].to_numpy(dtype=float)
    fs = estimate_fs(t)
    segments = split_segments(t, fs)
    out: dict[str, pd.DataFrame] = {}
    signals: dict[str, np.ndarray] = {}
    for ch in PPG_CHANNELS:
        if ch not in df.columns:
            continue
        raw = df[ch].to_numpy(dtype=float)
        filt = np.full_like(raw, np.nan)
        by_segment = []
        for seg in segments:
            filt[seg] = bandpass_filter(raw[seg], fs)
            by_segment.append((filt[seg], t[seg]))
        beat_t, ibi = beat_intervals(by_segment, fs)
        beats = pd.DataFrame(
            {
                "t": _to_host(anchor, beat_t),
                "ibi_ms": [np.nan if v is None else v for v in ibi],
            }
        )
        out[ch] = beats
        signals[ch] = filt
    return out, signals, _to_host(anchor, t), fs


def load_sense_ppi(session_dir: Path, meta: dict[str, Any]) -> pd.DataFrame:
    """Sense PPI (``t``, ``ppi_ms`` NaN when invalid or after a gap, ``contact``)."""
    path = session_dir / "sense" / "raw" / "ppi.csv"
    anchor = host_zero(meta, "sense_ppi")
    if not path.exists() or anchor is None:
        return pd.DataFrame(columns=["t", "ppi_ms", "contact"])
    raw = pd.read_csv(path)
    ppi = pd.to_numeric(raw["PPI_ms"], errors="coerce")
    if "Invalid" in raw.columns:
        ppi = ppi.mask(pd.to_numeric(raw["Invalid"], errors="coerce") == 1)
    ts = raw["Timestamp_s"].to_numpy(dtype=float)
    # Lost packets: the time step is much longer than the interval it carries.
    step_ms = np.diff(ts, prepend=np.nan) * 1000.0
    ppi = ppi.mask(step_ms > 1.5 * ppi.to_numpy() + 100.0)
    contact = (
        pd.to_numeric(raw["SkinContact"], errors="coerce")
        if "SkinContact" in raw
        else pd.Series(np.nan, index=raw.index)
    )
    return pd.DataFrame({"t": _to_host(anchor, ts), "ppi_ms": ppi, "contact": contact})


def load_motion(session_dir: Path, meta: dict[str, Any]) -> pd.Series:
    """Per-second SD of the Sense acceleration magnitude (mG), indexed by host second."""
    path = session_dir / "sense" / "raw" / "acc.csv"
    anchor = host_zero(meta, "sense_acc")
    if not path.exists() or anchor is None:
        return _EMPTY_SERIES.copy()
    acc = pd.read_csv(path)
    mag = (acc["X_mG"] ** 2 + acc["Y_mG"] ** 2 + acc["Z_mG"] ** 2) ** 0.5
    t = _to_host(anchor, acc["Timestamp_s"])
    return mag.groupby(t.floor("1s")).std()


def _interval_stats(seq: list[float | None], window_s: float) -> dict[str, float]:
    """HR, RMSSD and coverage from one window's interval sequence (None = gap)."""
    valid = rr_valid_mask(seq)
    vals = [v for v, ok in zip(seq, valid, strict=True) if ok and v is not None]
    return {
        "hr": 60000.0 / float(np.mean(vals)) if vals else float("nan"),
        "rmssd": calculate_rmssd(seq),
        "n": float(len(vals)),
        "coverage": float(sum(vals) / (window_s * 1000.0)),
    }


def _seq(values: pd.Series) -> list[float | None]:
    return [None if pd.isna(v) else float(v) for v in values]


def _summary_hr(session_dir: Path, device: str) -> pd.Series:
    path = session_dir / device / "post-processed" / "summary.csv"
    if not path.exists():
        return _EMPTY_SERIES.copy()
    df = pd.read_csv(path, parse_dates=["Timestamp"])
    hr = pd.to_numeric(df["HeartRate_BPM"], errors="coerce")
    return pd.Series(hr.where(hr > 0).to_numpy(), index=df["Timestamp"])


def build_windows(session_dir: Path | str, window_s: int = WINDOW_S) -> pd.DataFrame:
    """One row per window with reference, test and artifact columns.

    Columns (``ref_*`` = H10 RR, ``ppg_*`` = raw-PPG beats on the best channel,
    ``ppi_*`` = Sense PPI stream, ``*_reported_hr`` = device-computed HR):
    ``start, ref_hr, ref_rmssd, ref_n, ref_coverage, ref_ok, ppg_channel,
    ppg_sqi, ppg_hr, ppg_hr_spectral, ppg_rmssd, ppg_n, ppg_coverage,
    motion_frac, artifact, artifact_reason, ppi_hr, ppi_rmssd, ppi_coverage,
    contact_frac, ppi_artifact, h10_reported_hr, sense_reported_hr, markers``.
    """
    session_dir = Path(session_dir)
    meta = _read_meta(session_dir)
    ref = load_h10_beats(session_dir, meta)
    ppg, signals, sig_t, fs = load_ppg_channels(session_dir, meta)
    ppi = load_sense_ppi(session_dir, meta)
    motion = load_motion(session_dir, meta)
    h10_rep = _summary_hr(session_dir, "h10")
    sense_rep = _summary_hr(session_dir, "sense")

    tests = [b["t"] for b in ppg.values()] + ([ppi["t"]] if len(ppi) else [])
    if ref.empty or not tests:
        return pd.DataFrame()
    start = max(ref["t"].min(), *(t.min() for t in tests)).ceil("1s")
    end = min(ref["t"].max(), *(t.max() for t in tests))
    markers = [
        (datetime.fromtimestamp(m["timestamp_epoch_s"]), m["label"])
        for m in meta.get("markers", [])
        if "timestamp_epoch_s" in m
    ]

    rows = []
    win = pd.Timedelta(seconds=window_s)
    a = start
    while a + win <= end:
        b = a + win
        row: dict[str, Any] = {"start": a}

        r = _interval_stats(
            _seq(ref.loc[(ref["t"] >= a) & (ref["t"] < b), "rr_ms"]), window_s
        )
        row.update({f"ref_{k}": v for k, v in r.items()})
        row["ref_ok"] = r["coverage"] >= MIN_COVERAGE

        best: dict[str, Any] = {"ppg_sqi": float("nan")}
        for ch, beats in ppg.items():
            sig = signals[ch]
            in_win = (sig_t >= a) & (sig_t < b) & ~np.isnan(sig)
            sqi = spectral_sqi(sig[in_win], fs)
            if np.isnan(best["ppg_sqi"]) or sqi > best["ppg_sqi"]:
                s = _interval_stats(
                    _seq(beats.loc[(beats["t"] >= a) & (beats["t"] < b), "ibi_ms"]),
                    window_s,
                )
                best = {
                    "ppg_channel": ch,
                    "ppg_sqi": sqi,
                    "ppg_hr": s["hr"],
                    "ppg_hr_spectral": spectral_hr(sig[in_win], fs),
                    "ppg_rmssd": s["rmssd"],
                    "ppg_n": s["n"],
                    "ppg_coverage": s["coverage"],
                }
        row.update(best)

        m = motion[(motion.index >= a) & (motion.index < b)]
        row["motion_frac"] = (
            float((m > MOTION_SD_MG).mean()) if len(m) else float("nan")
        )
        reasons = []
        if not row["motion_frac"] <= MOTION_MAX_FRAC:
            reasons.append("motion")
        if not row.get("ppg_sqi", np.nan) >= SQI_MIN:
            reasons.append("low_sqi")
        if not row.get("ppg_coverage", np.nan) >= MIN_COVERAGE:
            reasons.append("low_coverage")
        row["artifact"] = bool(reasons)
        row["artifact_reason"] = ",".join(reasons)

        if len(ppi):
            w = ppi[(ppi["t"] >= a) & (ppi["t"] < b)]
            p = _interval_stats(_seq(w["ppi_ms"]), window_s)
            row.update(
                {
                    "ppi_hr": p["hr"],
                    "ppi_rmssd": p["rmssd"],
                    "ppi_coverage": p["coverage"],
                }
            )
            contact = w["contact"].dropna()
            row["contact_frac"] = (
                float((contact == 1).mean()) if len(contact) else float("nan")
            )
            row["ppi_artifact"] = bool(
                not row["motion_frac"] <= MOTION_MAX_FRAC
                or not p["coverage"] >= MIN_COVERAGE
                or row["contact_frac"] < MIN_CONTACT_FRAC
            )

        for col, rep in (
            ("h10_reported_hr", h10_rep),
            ("sense_reported_hr", sense_rep),
        ):
            v = rep[(rep.index >= a) & (rep.index < b)]
            row[col] = float(v.mean()) if v.notna().any() else float("nan")
        row["markers"] = ";".join(lbl for t, lbl in markers if a <= t < b)
        rows.append(row)
        a = b
    return pd.DataFrame(rows)
