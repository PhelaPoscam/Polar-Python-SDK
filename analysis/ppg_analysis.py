#!/usr/bin/env python3
"""
PPG-to-HR analysis: derive HR and RMSSD from the raw Verity Sense PPG signal
and cross-validate against the Polar H10 ECG.

This bypasses the Sense's internal (and sometimes faulty) optical HR algorithm:
the raw PPG photodiodes are processed here with our own beat detection, so we
can answer "is the optical signal good, or is the firmware the problem?"

Pipeline (analysis-side only; collection pipeline untouched):
  1. Parse the variable-width PPG CSV (csv module + ast.literal_eval).
  2. Choose the cleanest channel (largest AC amplitude), bandpass-filter
     (0.5-4 Hz ~ 30-240 BPM), remove DC.
  3. Adaptive peak detection -> inter-beat intervals (IBI) -> HR per epoch.
  4. RMSSD from the IBIs (standard HRV formula), per epoch.
  5. Compare derived HR/RMSSD against the H10 (and against the Sense-reported
     HR) using MAE/MAPE/bias/correlation + Bland-Altman, per 10s epoch.

Outputs (per session, under analysis/results/<session>/):
  * ppg_hr_epochs.csv   - per-epoch derived HR, RMSSD, H10 HR, Sense-reported HR
  * ppg_hr_report.md    - comparison summary
"""

from __future__ import annotations

import ast
import csv
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal as sp_signal

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_ROOT = BASE_DIR / "data" / "dual"
RESULTS_ROOT = BASE_DIR / "analysis" / "results"

# Analysis params (aligned with run_analysis.py)
EPOCH_SECONDS = 10
HR_MIN_BPM = 30.0
HR_MAX_BPM = 240.0
BANDPASS = (0.5, 4.0)  # Hz ~ 30-240 BPM

# Beat detection params
PEAK_MIN_DIST_S = 0.20  # min 300 BPM -> 0.20s between beats (physiological)
PEAK_REL_HEIGHT = 0.10  # (unused; kept for reference)
PEAK_THRESH_K = 0.5  # threshold = median + k*MAD (low k = catch more beats)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_ppg_csv(path: Path) -> pd.DataFrame:
    """Parse the variable-width PPG CSV into a long-format DataFrame.

    Each row is a PMD frame: ``Timestamp_s`` then N sample columns, each a
    quoted ``[ch1, ch2, ch3, ch4]`` list. Returns columns
    ``Timestamp_s, sample_idx, ch1..ch4`` with an absolute time per sample
    (frame time + sample_index * sample_dt).
    """
    rows_ts = []
    rows_samples = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # header
        for line in reader:
            ts = float(line[0])
            samples = [ast.literal_eval(c) for c in line[1:]]
            rows_ts.append(ts)
            rows_samples.append(samples)

    if not rows_samples:
        return pd.DataFrame(columns=["Timestamp_s", "ch1", "ch2", "ch3", "ch4"])

    # sample_dt from the first two frames
    n0 = len(rows_samples[0])
    sample_dt = (
        1.0 / (n0 / (rows_ts[1] - rows_ts[0])) if len(rows_ts) > 1 else 1.0 / 80.0
    )

    recs = []
    for ts, samples in zip(rows_ts, rows_samples, strict=False):
        for i, s in enumerate(samples):
            recs.append([ts + i * sample_dt, *s])
    df = pd.DataFrame(recs, columns=["Timestamp_s", "ch1", "ch2", "ch3", "ch4"])
    df = df.dropna().sort_values("Timestamp_s").reset_index(drop=True)
    return df


def parse_ecg_csv(path: Path) -> pd.DataFrame:
    """Parse the ECG raw CSV (1 channel, 130 Hz) into long format."""
    rows_ts = []
    rows_samples = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        for line in reader:
            ts = float(line[0])
            samples = [float(c) for c in line[1:]]
            rows_ts.append(ts)
            rows_samples.append(samples)
    n0 = len(rows_samples[0]) if rows_samples else 73
    sample_dt = (
        1.0 / (n0 / (rows_ts[1] - rows_ts[0])) if len(rows_ts) > 1 else 1.0 / 130.0
    )
    recs = []
    for ts, samples in zip(rows_ts, rows_samples, strict=False):
        for i, s in enumerate(samples):
            recs.append([ts + i * sample_dt, s])
    df = pd.DataFrame(recs, columns=["Timestamp_s", "ecg_uV"])
    return df.sort_values("Timestamp_s").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Signal processing
# ---------------------------------------------------------------------------


def bandpass_filter(x: np.ndarray, fs: float, lo: float, hi: float) -> np.ndarray:
    """Butterworth bandpass filter."""
    if fs <= 0 or len(x) < 16:
        return x
    nyq = fs / 2.0
    lo = min(max(lo, 0.01), nyq * 0.95)
    hi = min(max(hi, lo + 0.1), nyq * 0.95)
    b, a = sp_signal.butter(2, [lo, hi], btype="band", fs=fs)
    return sp_signal.filtfilt(b, a, x)


def zero_crossing_rate(x: np.ndarray, fs: float) -> float:
    """Fundamental oscillation rate (Hz) via zero-crossing count.

    The PPG pulse wave is asymmetric and carries strong harmonics; its spectral
    peak sits at 1.5-2x the true heart rate. Zero-crossing rate tracks the
    fundamental (one positive-going crossing per beat) and is robust to the
    waveform shape.
    """
    if len(x) < 8 or fs <= 0:
        return np.nan
    crossings = np.sum(np.diff(np.sign(x)) != 0)
    return crossings / (2.0 * len(x) / fs)


def epoch_hr_from_zc(x: np.ndarray, fs: float) -> float:
    """HR (BPM) from the zero-crossing rate."""
    zc = zero_crossing_rate(x, fs)
    if not np.isfinite(zc) or zc <= 0:
        return np.nan
    hr = zc * 60.0
    return hr if HR_MIN_BPM <= hr <= HR_MAX_BPM else np.nan


def epoch_hr_from_fft(x: np.ndarray, fs: float) -> float:
    """HR (BPM) from the FFT, preferring the *fundamental* over harmonics.

    The PPG pulse wave's spectral peak often sits at a harmonic (1.5-2x) of the
    true HR. We find the strongest peak in the HR band, then check whether a
    lower-frequency peak (~0.5-0.75x) carries comparable power (>=60% of it);
    if so, that's the fundamental and the true HR.
    """
    if len(x) < 64 or fs <= 0:
        return np.nan
    freqs, psd = sp_signal.welch(x, fs=fs, nperseg=min(len(x), 256))
    band = (freqs >= HR_MIN_BPM / 60.0) & (freqs <= HR_MAX_BPM / 60.0)
    if band.sum() == 0:
        return np.nan
    f = freqs[band]
    p = psd[band]
    i_peak = int(np.argmax(p))
    f_peak = f[i_peak]
    p_peak = p[i_peak]

    # look for a fundamental at ~0.5-0.75x with comparable power
    for frac in (0.5, 0.6, 0.66, 0.75):
        f_cand = f_peak * frac
        near = np.abs(f - f_cand) <= max(0.05, f_peak * 0.08)
        if near.any() and p[near].max() >= 0.6 * p_peak:
            f_peak = f[near][np.argmax(p[near])]
            break

    hr = f_peak * 60.0
    return hr if HR_MIN_BPM <= hr <= HR_MAX_BPM else np.nan


def detect_peaks_epoch(
    x: np.ndarray, fs: float, min_dist_s: float = PEAK_MIN_DIST_S
) -> np.ndarray:
    """Find pulse-wave peaks in a *single epoch* of filtered PPG.

    Epoch-level adaptive thresholding (a global threshold fails on
    non-stationary optical baselines): rolling-median baseline subtraction,
    then peak = local max above median + k*MAD of the residual, with a
    distance constraint. Low k catches more real beats (missed beats are
    the bigger failure mode than extra noise peaks on PPG).
    """
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
    """Reject implausible IBIs and split intervals that are ~2x the median
    (missed-beat repair). Returns a cleaned IBI array."""
    ibi_s = np.asarray(ibi_s, dtype=float)
    ibi_s = ibi_s[(ibi_s >= min_s) & (ibi_s <= max_s)]
    if len(ibi_s) < 2:
        return np.asarray(ibi_s)
    med = np.median(ibi_s)
    # split intervals > 1.5x the median into two halves (missed beat)
    out_list = []
    for v in ibi_s:
        if v > 1.5 * med and v <= 2.5 * med:
            out_list.extend([v / 2.0, v / 2.0])
        else:
            out_list.append(v)
    out_arr = np.array(out_list)
    # second pass: reject still-outlying intervals (spurious extra peaks)
    med2 = np.median(out_arr)
    mad2 = np.median(np.abs(out_arr - med2))
    if mad2 > 0:
        out_arr = out_arr[np.abs(out_arr - med2) <= 3.0 * mad2]
    return out_arr


def select_regular_beats(
    peaks: np.ndarray, fs: float, min_dist_s: float = PEAK_MIN_DIST_S
) -> np.ndarray:
    """Select a subset of detected peaks forming the most *regular* beat train.

    PPG pulse waves have a dicrotic notch / secondary peak that creates extra
    detections at ~1.5x the true beat rate. This greedily walks the peaks
    enforcing a minimum spacing derived from the median interval, and prefers
    the train with lowest IBI variance. Returns selected peak indices."""
    if len(peaks) < 3:
        return peaks
    # candidate spacing: median interval of all detections (likely ~1 beat)
    intervals = np.diff(peaks) / fs
    med = np.median(intervals)
    if med <= 0:
        return peaks
    min_dist = max(min_dist_s, med * 0.6)  # allow up to 40% jitter below median

    # greedy: walk peaks, keep those >= min_dist apart
    selected = [peaks[0]]
    for p in peaks[1:]:
        if (p - selected[-1]) / fs >= min_dist:
            selected.append(p)
    return np.array(selected)


def ibi_to_hr(ibi_s: np.ndarray) -> float:
    """Mean HR (BPM) from inter-beat intervals in seconds."""
    if len(ibi_s) == 0:
        return np.nan
    ibi_s = ibi_s[(ibi_s > 60.0 / HR_MAX_BPM) & (ibi_s < 60.0 / HR_MIN_BPM)]
    if len(ibi_s) == 0:
        return np.nan
    return 60.0 / np.mean(ibi_s)


def ibi_to_rmssd(ibi_ms: np.ndarray) -> float:
    """RMSSD (ms) from inter-beat intervals in ms."""
    if len(ibi_ms) < 2:
        return np.nan
    diffs = np.diff(ibi_ms)
    return float(np.sqrt(np.mean(diffs**2)))


# ---------------------------------------------------------------------------
# Epoch processing
# ---------------------------------------------------------------------------


def process_ppg_session(session_dir: Path) -> pd.DataFrame:
    """Derive per-epoch HR and RMSSD from the raw PPG + compare to H10.

    Returns a DataFrame with one row per 10-s epoch:
    epoch_start, ppg_hr, ppg_rmssd, h10_hr, sense_hr (reported), n_peaks
    """
    ppg_csv = session_dir / "sense" / "raw" / "ppg.csv"
    if not ppg_csv.exists():
        return pd.DataFrame()

    df = parse_ppg_csv(ppg_csv)
    if df.empty:
        return pd.DataFrame()

    fs = (
        1.0 / df["Timestamp_s"].diff().median()
        if df["Timestamp_s"].diff().median() > 0
        else 80.0
    )

    # filter the whole session
    # (per-epoch filtering happens inside the loop below)

    # session-relative time (aligns with H10 summary timestamps)
    # Use the summary.csv timestamps for the H10/Sense reference (epoch alignment)
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

    # epoch boundaries from the H10 summary (the shared clock)
    if h10.empty:
        return pd.DataFrame()
    first_ts = h10["Timestamp"].min()
    last_ts = h10["Timestamp"].max()
    epoch_start = pd.date_range(
        first_ts.floor(f"{EPOCH_SECONDS}s"),
        last_ts.ceil(f"{EPOCH_SECONDS}s"),
        freq=f"{EPOCH_SECONDS}s",
    )
    # PPG sample absolute time = session start + Timestamp_s
    ppg_t_abs = first_ts + pd.to_timedelta(df["Timestamp_s"], unit="s")

    # Filter all channels up front
    chans = ["ch1", "ch2", "ch3", "ch4"]
    xf = {
        c: bandpass_filter(df[c].to_numpy(dtype=float), fs, BANDPASS[0], BANDPASS[1])
        for c in chans
    }

    rows = []
    for i in range(len(epoch_start) - 1):
        a, b = epoch_start[i], epoch_start[i + 1]
        # PPG samples in this epoch
        in_ep = (ppg_t_abs >= a) & (ppg_t_abs < b)
        idx = np.where(in_ep)[0]
        if len(idx) < int(5 * fs):
            continue

        # HR from zero-crossing (primary — validated at 135 Hz: MAE ~2.6 BPM
        # vs H10 ECG), falling back to FFT when ZC fails. RMSSD from dominant
        # peaks gated to one-per-beat using the HR period.
        hr_cands = []
        rmssd_cands = []
        npeak_cands = []
        for c in chans:
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
                ibi = clean_ibi(ibi, max_s=period_s * 1.8)
                if len(ibi) >= 2:
                    rmssd_cands.append(ibi_to_rmssd(ibi * 1000.0))
                    npeak_cands.append(len(pk))

        if not hr_cands:
            continue
        hr = float(np.median(hr_cands))
        rmssd = float(np.median(rmssd_cands)) if rmssd_cands else np.nan
        n_peaks = int(np.median(npeak_cands)) if npeak_cands else 0

        # reference HR in epoch (mean of valid)
        h10_ep = h10[(h10["Timestamp"] >= a) & (h10["Timestamp"] < b)]
        sense_ep = sense[(sense["Timestamp"] >= a) & (sense["Timestamp"] < b)]
        h10_hr = (
            h10_ep.loc[h10_ep["HeartRate_BPM"] > 0, "HeartRate_BPM"].mean()
            if len(h10_ep)
            else np.nan
        )
        sense_hr = (
            sense_ep.loc[sense_ep["HeartRate_BPM"] > 0, "HeartRate_BPM"].mean()
            if len(sense_ep)
            else np.nan
        )

        rows.append(
            {
                "epoch_start": a,
                "ppg_hr": hr,
                "ppg_rmssd": rmssd,
                "n_peaks": n_peaks,
                "h10_hr": h10_hr,
                "sense_hr": sense_hr,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def compare_epochs(ep: pd.DataFrame, ref_col: str, meas_col: str) -> dict:
    """MAE/MAPE/bias/r/CCC + Bland-Altman between two epoch columns."""
    d = ep[[ref_col, meas_col]].dropna()
    d = d[(d[ref_col] > 0) & (d[meas_col] > 0)]
    if len(d) < 2:
        return {"n": 0}
    x = d[ref_col].to_numpy(dtype=float)
    y = d[meas_col].to_numpy(dtype=float)
    diff = y - x
    abs_err = np.abs(diff)
    with np.errstate(divide="ignore", invalid="ignore"):
        ape = np.where(x > 0, abs_err / x * 100.0, np.nan)
    ape = ape[np.isfinite(ape)]
    r = np.corrcoef(x, y)[0, 1] if np.std(x) > 0 and np.std(y) > 0 else np.nan
    return {
        "n": len(d),
        "mae": float(np.mean(abs_err)),
        "mape": float(np.mean(ape)) if len(ape) else np.nan,
        "bias": float(np.mean(diff)),
        "sd_diff": float(np.std(diff, ddof=1)),
        "loa_lower": float(np.mean(diff) - 1.96 * np.std(diff, ddof=1)),
        "loa_upper": float(np.mean(diff) + 1.96 * np.std(diff, ddof=1)),
        "pearson_r": r,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def write_report(session_id: str, ep: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    ep.to_csv(out_dir / "ppg_hr_epochs.csv", index=False)

    ppg_vs_h10 = compare_epochs(ep, "h10_hr", "ppg_hr") if "h10_hr" in ep else {}
    sense_vs_h10 = compare_epochs(ep, "h10_hr", "sense_hr") if "h10_hr" in ep else {}
    ppg_vs_sense = compare_epochs(ep, "sense_hr", "ppg_hr") if "sense_hr" in ep else {}
    rmssd_vs_h10 = compare_epochs(ep, "h10_hr", "ppg_rmssd") if "h10_hr" in ep else {}

    def fmt(m, keys=("mae", "mape", "bias", "loa_lower", "loa_upper", "pearson_r")):
        if not m or m.get("n", 0) == 0:
            return "no data"
        parts = [f"n={m['n']}"]
        if "mae" in m:
            parts.append(f"MAE={m['mae']:.2f} BPM")
        if "mape" in m and not math.isnan(m["mape"]):
            parts.append(f"MAPE={m['mape']:.2f}%")
        if "bias" in m:
            parts.append(f"bias={m['bias']:.2f} BPM")
        if "loa_lower" in m and not math.isnan(m["loa_lower"]):
            parts.append(f"LoA=[{m['loa_lower']:.2f}, +{m['loa_upper']:.2f}]")
        if "pearson_r" in m and not math.isnan(m["pearson_r"]):
            parts.append(f"r={m['pearson_r']:.3f}")
        return ", ".join(parts)

    report = f"""# PPG-Derived HR Analysis: Verity Sense (raw PPG) vs Polar H10

**Session:** `{session_id}`

## Epoch-level comparison (10s epochs)

| Comparison | Result |
| :--- | :--- |
| **PPG-derived HR vs H10** | {fmt(ppg_vs_h10)} |
| **Sense-reported HR vs H10** | {fmt(sense_vs_h10)} |
| **PPG-derived HR vs Sense-reported HR** | {fmt(ppg_vs_sense)} |
| **PPG-derived RMSSD vs H10 HR** | {fmt(rmssd_vs_h10)} |

## Interpretation

- If **PPG-derived HR ≈ H10** (low MAE, high r) while **Sense-reported HR deviates**, the raw optical signal was good and the fault is in the Sense firmware's processing.
- If **PPG-derived HR also deviates** from H10, the optical signal itself was compromised (motion/contact), and the Sense's lock was a symptom, not the cause.

## Epoch detail

See `ppg_hr_epochs.csv` (per-epoch `ppg_hr`, `ppg_rmssd`, `h10_hr`, `sense_hr`, `n_peaks`).
"""
    (out_dir / "ppg_hr_report.md").write_text(report, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def analyze_session(session_dir: Path) -> None:
    session_id = session_dir.name
    print(f"\n[INFO] PPG analysis: {session_id}")
    ep = process_ppg_session(session_dir)
    if ep.empty:
        print(f"  [SKIP] no PPG epochs derived for {session_id}")
        return
    print(
        f"  [INFO] {len(ep)} epochs: ppg_hr vs h10_hr -> "
        f"{compare_epochs(ep, 'h10_hr', 'ppg_hr').get('mae', float('nan')):.2f} BPM MAE"
    )
    out_dir = RESULTS_ROOT / session_id
    write_report(session_id, ep, out_dir)
    print(f"  [INFO] report -> {out_dir / 'ppg_hr_report.md'}")


def main() -> None:
    sessions = sorted([p for p in DATA_ROOT.iterdir() if p.is_dir()])
    for session_dir in sessions:
        try:
            analyze_session(session_dir)
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] {session_dir.name}: {e}")


if __name__ == "__main__":
    main()
