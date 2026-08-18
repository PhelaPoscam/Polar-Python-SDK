"""PPG-to-HR and HRV analysis: derive HR and RMSSD from raw Verity Sense optical signals.

Extracts pulse waves, computes zero-crossing rates, FFT fundamentals, adaptive peak detection,
IBI cleaning, and RMSSD calculation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import signal as sp_signal

from polar_ble_sdk.research.loader import _parse_wide_ppg_csv

EPOCH_SECONDS = 10
HR_MIN_BPM = 30.0
HR_MAX_BPM = 240.0
BANDPASS = (0.5, 4.0)  # Hz ~ 30-240 BPM
PEAK_MIN_DIST_S = 0.20
PEAK_THRESH_K = 0.5


def bandpass_filter(
    x: np.ndarray, fs: float, lo: float = BANDPASS[0], hi: float = BANDPASS[1]
) -> np.ndarray:
    """Butterworth bandpass filter for physiological HR frequency range."""
    if fs <= 0 or len(x) < 16:
        return x
    nyq = fs / 2.0
    lo = min(max(lo, 0.01), nyq * 0.95)
    hi = min(max(hi, lo + 0.1), nyq * 0.95)
    b, a = sp_signal.butter(2, [lo, hi], btype="band", fs=fs)
    return sp_signal.filtfilt(b, a, x)


def zero_crossing_rate(x: np.ndarray, fs: float) -> float:
    """Fundamental oscillation rate (Hz) via zero-crossing count."""
    if len(x) < 8 or fs <= 0:
        return float("nan")
    crossings = np.sum(np.diff(np.sign(x)) != 0)
    return float(crossings / (2.0 * len(x) / fs))


def epoch_hr_from_zc(x: np.ndarray, fs: float) -> float:
    """Heart rate (BPM) from the zero-crossing rate."""
    zc = zero_crossing_rate(x, fs)
    if not np.isfinite(zc) or zc <= 0:
        return float("nan")
    hr = zc * 60.0
    return float(hr) if HR_MIN_BPM <= hr <= HR_MAX_BPM else float("nan")


def epoch_hr_from_fft(x: np.ndarray, fs: float) -> float:
    """Heart rate (BPM) from Welch PSD, tracking the fundamental frequency."""
    if len(x) < 64 or fs <= 0:
        return float("nan")
    freqs, psd = sp_signal.welch(x, fs=fs, nperseg=min(len(x), 256))
    band = (freqs >= HR_MIN_BPM / 60.0) & (freqs <= HR_MAX_BPM / 60.0)
    if band.sum() == 0:
        return float("nan")
    f = freqs[band]
    p = psd[band]
    i_peak = int(np.argmax(p))
    f_peak = f[i_peak]
    p_peak = p[i_peak]

    for frac in (0.5, 0.6, 0.66, 0.75):
        f_cand = f_peak * frac
        near = np.abs(f - f_cand) <= max(0.05, f_peak * 0.08)
        if near.any() and p[near].max() >= 0.6 * p_peak:
            f_peak = f[near][np.argmax(p[near])]
            break

    hr = f_peak * 60.0
    return float(hr) if HR_MIN_BPM <= hr <= HR_MAX_BPM else float("nan")


def detect_peaks_epoch(
    x: np.ndarray, fs: float, min_dist_s: float = PEAK_MIN_DIST_S
) -> np.ndarray:
    """Find pulse-wave peaks in a single epoch of filtered PPG using rolling MAD thresholding."""
    if len(x) < 32 or fs <= 0:
        return np.array([], dtype=int)
    min_dist = max(int(min_dist_s * fs), 1)

    win = max(int(1.5 * fs), 7)
    if win % 2 == 0:
        win += 1
    baseline = pd.Series(x).rolling(win, center=True, min_periods=1).median().to_numpy()
    resid = x - baseline
    mad = np.median(np.abs(resid - np.median(resid)))
    if mad <= 0:
        mad = resid.std()
    thr = np.median(resid) + PEAK_THRESH_K * mad
    peaks, _ = sp_signal.find_peaks(resid, distance=min_dist, height=thr)
    return peaks


def clean_ibi(ibi_s: np.ndarray, min_s: float = 0.25, max_s: float = 2.0) -> np.ndarray:
    """Reject physiological outliers and repair missed-beat intervals (~2x median)."""
    ibi_s = np.asarray(ibi_s, dtype=float)
    ibi_s = ibi_s[(ibi_s >= min_s) & (ibi_s <= max_s)]
    if len(ibi_s) < 2:
        return np.asarray(ibi_s)
    med = np.median(ibi_s)
    out_list: list[float] = []
    for v in ibi_s:
        if 1.5 * med < v <= 2.5 * med:
            out_list.extend([v / 2.0, v / 2.0])
        else:
            out_list.append(v)
    out_arr = np.array(out_list)
    med2 = np.median(out_arr)
    mad2 = np.median(np.abs(out_arr - med2))
    cutoff = max(3.0 * mad2, 0.25 * med2)
    out_arr = out_arr[np.abs(out_arr - med2) <= cutoff]
    return out_arr


def ibi_to_hr(ibi_s: np.ndarray) -> float:
    """Mean HR (BPM) from inter-beat intervals in seconds."""
    if len(ibi_s) == 0:
        return float("nan")
    valid_ibi = ibi_s[(ibi_s > 60.0 / HR_MAX_BPM) & (ibi_s < 60.0 / HR_MIN_BPM)]
    if len(valid_ibi) == 0:
        return float("nan")
    return float(60.0 / np.mean(valid_ibi))


def ibi_to_rmssd(ibi_ms: np.ndarray) -> float:
    """RMSSD (ms) from inter-beat intervals in milliseconds."""
    if len(ibi_ms) < 2:
        return float("nan")
    diffs = np.diff(ibi_ms)
    return float(np.sqrt(np.mean(diffs**2)))


def derive_ppg_hr_epochs(session_dir: Path) -> pd.DataFrame:
    """Derive per-epoch HR and RMSSD from raw PPG and compare to H10 ECG reference."""
    ppg_csv = session_dir / "sense" / "raw" / "ppg.csv"
    if not ppg_csv.exists():
        return pd.DataFrame()

    df = _parse_wide_ppg_csv(ppg_csv)
    if df.empty:
        return pd.DataFrame()

    diffs = df["Timestamp_s"].diff().dropna()
    fs = float(1.0 / diffs.median()) if len(diffs) > 0 and diffs.median() > 0 else 80.0

    h10_csv = session_dir / "h10" / "post-processed" / "summary.csv"
    sense_csv = session_dir / "sense" / "post-processed" / "summary.csv"

    h10 = (
        pd.read_csv(h10_csv, parse_dates=["Timestamp"])
        if h10_csv.exists()
        else pd.DataFrame()
    )
    sense = (
        pd.read_csv(sense_csv, parse_dates=["Timestamp"])
        if sense_csv.exists()
        else pd.DataFrame()
    )

    if h10.empty:
        return pd.DataFrame()

    first_ts = h10["Timestamp"].min()
    last_ts = h10["Timestamp"].max()
    epoch_start = pd.date_range(
        first_ts.floor(f"{EPOCH_SECONDS}s"),
        last_ts.ceil(f"{EPOCH_SECONDS}s"),
        freq=f"{EPOCH_SECONDS}s",
    )
    ppg_t_abs = first_ts + pd.to_timedelta(df["Timestamp_s"], unit="s")

    chans = ["ch1", "ch2", "ch3", "ch4"]
    xf = {
        c: bandpass_filter(df[c].to_numpy(dtype=float), fs, BANDPASS[0], BANDPASS[1])
        for c in chans
        if c in df.columns
    }

    rows: list[dict[str, Any]] = []
    for i in range(len(epoch_start) - 1):
        a, b = epoch_start[i], epoch_start[i + 1]
        in_ep = (ppg_t_abs >= a) & (ppg_t_abs < b)
        idx = np.where(in_ep)[0]
        if len(idx) < int(5 * fs):
            continue

        hr_cands: list[float] = []
        rmssd_cands: list[float] = []
        npeak_cands: list[int] = []
        for c in xf:
            seg = xf[c][idx]
            hr = epoch_hr_from_zc(seg, fs)
            if not np.isfinite(hr):
                hr = epoch_hr_from_fft(seg, fs)
            if not np.isfinite(hr):
                continue
            hr_cands.append(hr)
            period_s = 60.0 / hr
            pk = detect_peaks_epoch(seg, fs)
            if len(pk) >= 3:
                ibi = np.diff(idx[pk]) / fs
                ibi_cleaned = clean_ibi(ibi, max_s=period_s * 1.8)
                if len(ibi_cleaned) >= 2:
                    rmssd_cands.append(ibi_to_rmssd(ibi_cleaned * 1000.0))
                    npeak_cands.append(len(pk))

        if not hr_cands:
            continue

        hr = float(np.median(hr_cands))
        rmssd = float(np.median(rmssd_cands)) if rmssd_cands else float("nan")
        n_peaks = int(np.median(npeak_cands)) if npeak_cands else 0

        h10_ep = h10[(h10["Timestamp"] >= a) & (h10["Timestamp"] < b)]
        sense_ep = sense[(sense["Timestamp"] >= a) & (sense["Timestamp"] < b)]
        h10_hr = (
            float(h10_ep.loc[h10_ep["HeartRate_BPM"] > 0, "HeartRate_BPM"].mean())
            if len(h10_ep)
            else float("nan")
        )
        sense_hr = (
            float(sense_ep.loc[sense_ep["HeartRate_BPM"] > 0, "HeartRate_BPM"].mean())
            if len(sense_ep)
            else float("nan")
        )

        rows.append(
            {
                "epoch_start": a,
                "ppg_hr": hr,
                "ppg_rmssd": rmssd,
                "h10_hr": h10_hr,
                "sense_hr": sense_hr,
                "n_peaks": n_peaks,
            }
        )

    return pd.DataFrame(rows)
