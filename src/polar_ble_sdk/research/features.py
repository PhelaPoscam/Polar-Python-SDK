"""Per-window ECG morphology, HRV, spectral, wavelet, EMD and statistical features.

One row per window on the host clock (the grid of :func:`build_windows` when
given its ``start`` column). Column prefixes name the source:

- ``ecg_``: H10 ECG (single chest lead, 130 Hz). Waves are delineated with
  NeuroKit2 (DWT method) per contiguous segment; lost BLE frames split the
  signal so no beat spans a gap. Values are per-window medians over beats.
  At 130 Hz one sample is 7.7 ms, which bounds every interval's precision.
  ``ecg_st_*`` is informational only: a single filtered lead is not diagnostic.
- ``rr_`` (H10 RR), ``ppi_`` (Sense PPI stream), ``ppgbeat_`` (beats found in
  raw Sense PPG): HRV. Time domain and Poincaré on the window itself; spectral
  power, sample entropy and DFA α1 (``*_5m``) on a 300 s window centred on it,
  shifted to stay inside the recording, NaN when valid beats cover < 80 % of it.
- ``ppg_``: band-passed raw Sense PPG, best channel per window by spectral SQI.
- ``h10_acc_``, ``sense_acc_``, ``sense_gyro_``: magnitude statistics.

Every ECG row is written; ``ecg_artifact`` marks windows where fewer than half
the beats were fully delineated, NeuroKit2's quality is < 0.5, or the H10
accelerometer shows motion. Filtering on it is left to the analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import neurokit2 as nk
import numpy as np
import pandas as pd
import pywt
from PyEMD import EMD
from scipy import fft as sp_fft
from scipy import integrate as sp_integrate
from scipy import signal as sp_signal
from scipy import stats as sp_stats

from polar_ble_sdk.metrics.hrv import (
    calculate_pnn50,
    calculate_rmssd,
    calculate_sdnn,
    rr_valid_mask,
    successive_differences,
)
from polar_ble_sdk.research.loader import _parse_wide_ecg_csv, _read_stream_csv
from polar_ble_sdk.research.ppg import estimate_fs, spectral_sqi, split_segments
from polar_ble_sdk.research.windows import (
    MIN_COVERAGE,
    MOTION_MAX_FRAC,
    MOTION_SD_MG,
    WINDOW_S,
    _read_meta,
    _to_host,
    load_h10_beats,
    load_motion,
    load_ppg_channels,
    load_sense_ppi,
    stream_source,
)

LONG_WINDOW_S = 300  # Task Force minimum for LF power
VLF = (0.0033, 0.04)
LF = (0.04, 0.15)
HF = (0.15, 0.4)
PSD_FREQS = np.arange(0.0033, 0.5, 0.001)
TEMPLATE_S = (0.3, 0.5)  # beat template: 300 ms before R to 500 ms after (P..T)
ST_OFFSET_S = 0.06  # ST level at J + 60 ms
MIN_SIGNAL_S = 10.0
ECG_QUALITY_MIN = 0.5
ECG_GOOD_BEATS_MIN = 0.5
DWT_WAVELET, DWT_LEVEL = "db4", 5
N_IMFS = 4
N_PCS = 3
N_DCT = 8
FIDUCIALS = (
    "P_Onsets",
    "P_Peaks",
    "P_Offsets",
    "R_Onsets",
    "Q_Peaks",
    "S_Peaks",
    "R_Offsets",
    "T_Onsets",
    "T_Peaks",
    "T_Offsets",
)


@dataclass
class Signal:
    x: np.ndarray
    t: pd.DatetimeIndex
    fs: float


@dataclass
class SessionSignals:
    """Everything feature extraction reads, loaded once (the plots reuse it)."""

    ecg_beats: pd.DataFrame = field(default_factory=pd.DataFrame)
    ecg_templates: np.ndarray = field(default_factory=lambda: np.empty((0, 0)))
    ecg_fs: float = float("nan")
    ecg: Signal | None = None
    intervals: dict[str, pd.DataFrame] = field(default_factory=dict)  # t, ms
    ppg: dict[str, Signal] = field(default_factory=dict)
    imu: dict[str, pd.Series] = field(default_factory=dict)  # magnitude by host time
    h10_motion: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))


# --- ECG ---------------------------------------------------------------------


def _at(x: np.ndarray, idx: float) -> float:
    return float(x[int(idx)]) if np.isfinite(idx) and 0 <= idx < len(x) else np.nan


def delineate_segment(x: np.ndarray, fs: float) -> tuple[np.ndarray, pd.DataFrame]:
    """Cleaned ECG and one row per R peak of one contiguous segment.

    Rows hold sample indices of each fiducial (``P_Onsets`` ... ``T_Offsets``,
    ``R``), amplitudes vs the PR-segment baseline (µV), durations and intervals
    (ms), ``quality`` (NeuroKit2, 0..1) and ``complete`` (P onset, QRS onset/
    offset and T offset all found, in order).
    """
    sr = int(round(fs))
    clean = np.asarray(nk.ecg_clean(x, sampling_rate=sr), dtype=float)
    _, info = nk.ecg_peaks(clean, sampling_rate=sr)
    r = np.asarray(info["ECG_R_Peaks"], dtype=int)
    if len(r) < 4:
        return clean, pd.DataFrame()
    _, waves = nk.ecg_delineate(clean, r, sampling_rate=sr, method="dwt")
    quality = np.asarray(nk.ecg_quality(clean, rpeaks=r, sampling_rate=sr))

    df = pd.DataFrame({k: np.asarray(waves[f"ECG_{k}"], float) for k in FIDUCIALS})
    df["R"] = r.astype(float)
    ms = 1000.0 / fs

    rows = []
    for _, b in df.iterrows():
        p_off, r_on = b["P_Offsets"], b["R_Onsets"]
        if np.isfinite(p_off) and np.isfinite(r_on) and r_on > p_off:
            base = float(np.mean(clean[int(p_off) : int(r_on) + 1]))
        else:
            base = _at(clean, r_on)
        rows.append(
            {
                "r_amp": _at(clean, b["R"]) - base,
                "q_depth": base - _at(clean, b["Q_Peaks"]),
                "s_depth": base - _at(clean, b["S_Peaks"]),
                "p_amp": _at(clean, b["P_Peaks"]) - base,
                "t_amp": _at(clean, b["T_Peaks"]) - base,
                "st_level": _at(clean, b["R_Offsets"] + round(ST_OFFSET_S * fs)) - base,
            }
        )
    out = pd.concat([df, pd.DataFrame(rows, index=df.index)], axis=1)
    out["p_dur"] = (df["P_Offsets"] - df["P_Onsets"]) * ms
    out["qrs_dur"] = (df["R_Offsets"] - df["R_Onsets"]) * ms
    out["t_dur"] = (df["T_Offsets"] - df["T_Onsets"]) * ms
    out["pr"] = (df["R_Onsets"] - df["P_Onsets"]) * ms
    out["qt"] = (df["T_Offsets"] - df["R_Onsets"]) * ms
    rr_s = np.diff(r, prepend=np.nan) / fs
    out["rr"] = rr_s * 1000.0
    out["qtc_bazett"] = out["qt"] / np.sqrt(rr_s)
    out["qtc_fridericia"] = out["qt"] / np.cbrt(rr_s)
    out["quality"] = quality[r]
    out["complete"] = (
        (df["P_Onsets"] < df["R_Onsets"])
        & (df["R_Onsets"] < df["R"])
        & (df["R"] < df["R_Offsets"])
        & (df["R_Offsets"] < df["T_Offsets"])
    )
    return clean, out


def load_ecg(
    session_dir: Path, meta: dict[str, Any]
) -> tuple[Signal | None, pd.DataFrame, np.ndarray]:
    """Cleaned H10 ECG, per-beat table and beat templates (rows match the table).

    The beat table's ``t`` is the host time of the R peak and every fiducial is
    also given as ``<name>_ms``, its signed offset from R.
    """
    path, anchor = stream_source(session_dir, meta, "h10", "ecg")
    if not path.exists() or anchor is None:
        return None, pd.DataFrame(), np.empty((0, 0))
    raw = _parse_wide_ecg_csv(path).sort_values("Timestamp_s")
    t = raw["Timestamp_s"].to_numpy(dtype=float)
    x = raw["uV"].to_numpy(dtype=float)
    fs = estimate_fs(t)
    pre, post = (round(s * fs) for s in TEMPLATE_S)
    clean = np.full_like(x, np.nan)
    tables, templates = [], []
    for seg in split_segments(t, fs):
        if seg.stop - seg.start < MIN_SIGNAL_S * fs:
            continue
        clean[seg], beats = delineate_segment(x[seg], fs)
        if beats.empty:
            continue
        for r in beats["R"].astype(int):
            ok = r - pre >= 0 and r + post < seg.stop - seg.start
            templates.append(
                clean[seg][r - pre : r + post + 1]
                if ok
                else np.full(pre + post + 1, np.nan)
            )
        beats["t"] = _to_host(anchor, t[seg][beats["R"].astype(int)])
        for k in FIDUCIALS:
            beats[f"{k}_ms"] = (beats[k] - beats["R"]) * 1000.0 / fs
        tables.append(beats.drop(columns=[*FIDUCIALS, "R"]))
    if not tables:
        return None, pd.DataFrame(), np.empty((0, 0))
    keep = ~np.isnan(clean)
    signal = Signal(clean[keep], _to_host(anchor, t[keep]), fs)
    return signal, pd.concat(tables, ignore_index=True), np.vstack(templates)


ECG_MEDIANS = (
    "r_amp",
    "q_depth",
    "s_depth",
    "p_amp",
    "p_dur",
    "qrs_dur",
    "t_amp",
    "t_dur",
    "st_level",
    "pr",
    "qt",
    "qtc_bazett",
    "qtc_fridericia",
    *(f"{k}_ms" for k in FIDUCIALS),
)


def ecg_window_features(
    beats: pd.DataFrame, templates: np.ndarray, motion_frac: float
) -> dict[str, float]:
    """Medians of the per-beat measurements, quality flags, beat PCA and DCT."""
    if beats.empty:
        return {}
    out: dict[str, float] = {f"ecg_{k}": float(beats[k].median()) for k in ECG_MEDIANS}
    out["ecg_n_beats"] = float(len(beats))
    out["ecg_good_beats"] = float(beats["complete"].mean())
    out["ecg_quality"] = float(beats["quality"].median())
    out["ecg_artifact"] = bool(
        not out["ecg_good_beats"] >= ECG_GOOD_BEATS_MIN
        or not out["ecg_quality"] >= ECG_QUALITY_MIN
        or motion_frac > MOTION_MAX_FRAC
    )
    tpl = templates[~np.isnan(templates).any(axis=1)]
    if len(tpl) > N_PCS:
        s = np.linalg.svd(tpl - tpl.mean(axis=0), compute_uv=False)
        ev = s**2 / np.sum(s**2)
        out.update({f"ecg_pca{i + 1}_var": float(ev[i]) for i in range(N_PCS)})
        coef = sp_fft.dct(np.median(tpl, axis=0), norm="ortho")[:N_DCT]
        out.update({f"ecg_dct{i}": float(c) for i, c in enumerate(coef)})
    return out


# --- HRV ---------------------------------------------------------------------


def _valid(seq: list[float | None]) -> np.ndarray:
    return np.array(rr_valid_mask(seq), dtype=bool)


def hrv_short(seq: list[float | None]) -> dict[str, float]:
    """Time-domain HRV and Poincaré SD1/SD2 of one window (None = gap)."""
    vals = np.array([v for v, ok in zip(seq, _valid(seq), strict=True) if ok], float)
    if len(vals) < 2:
        return {}
    sdnn = calculate_sdnn(seq)
    diffs = successive_differences(seq)
    sd1 = float(np.std(diffs, ddof=1) / np.sqrt(2)) if len(diffs) > 1 else np.nan
    return {
        "mean_rr": float(vals.mean()),
        "hr": 60000.0 / float(vals.mean()),
        "sdnn": sdnn,
        "rmssd": calculate_rmssd(seq),
        "pnn50": calculate_pnn50(seq),
        "sd1": sd1,
        "sd2": float(np.sqrt(max(2 * sdnn**2 - sd1**2, 0.0))),
    }


def lomb_psd(t_s: np.ndarray, rr_ms: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Lomb-Scargle PSD (ms²/Hz) of unevenly spaced valid intervals.

    No interpolation across gaps or removed beats. Scaled so the PSD integrates
    to the series variance over ``PSD_FREQS``.
    """
    y = sp_signal.detrend(rr_ms)
    pgram = sp_signal.lombscargle(t_s, y, 2 * np.pi * PSD_FREQS)
    area = sp_integrate.trapezoid(pgram, PSD_FREQS)
    return PSD_FREQS, pgram * (np.var(y) / area if area > 0 else np.nan)


def _band(f: np.ndarray, p: np.ndarray, band: tuple[float, float]) -> float:
    m = (f >= band[0]) & (f < band[1])
    return float(sp_integrate.trapezoid(p[m], f[m]))


def hrv_long(t_s: np.ndarray, seq: list[float | None]) -> dict[str, float]:
    """Spectral power, sample entropy and DFA α1 over one long window."""
    ok = _valid(seq)
    if (
        ok.sum() < 50
        or np.nansum(np.array(seq, float)[ok]) < MIN_COVERAGE * LONG_WINDOW_S * 1000
    ):
        return {}
    vals = np.array(seq, float)[ok]
    f, p = lomb_psd(t_s[ok], vals)
    lf, hf = _band(f, p, LF), _band(f, p, HF)
    # ponytail: entropy/DFA run on valid beats joined across gaps; fine while gaps are rare
    return {
        "vlf_5m": _band(f, p, VLF),
        "lf_5m": lf,
        "hf_5m": hf,
        "lf_hf_5m": lf / hf if hf > 0 else np.nan,
        "total_power_5m": float(sp_integrate.trapezoid(p, f)),
        "sampen_5m": float(
            nk.entropy_sample(vals, dimension=2, tolerance=0.2 * np.std(vals))[0]
        ),
        "dfa_a1_5m": float(nk.fractal_dfa(vals, scale=np.arange(4, 17))[0]),
    }


# --- Generic signals ------------------------------------------------------------


def signal_features(x: np.ndarray, fs: float) -> dict[str, float]:
    """Statistics, Welch spectrum, DWT and EMD/Hilbert features of one segment."""
    if len(x) < MIN_SIGNAL_S * fs:
        return {}
    out = {
        "mean": float(np.mean(x)),
        "var": float(np.var(x)),
        "skew": float(sp_stats.skew(x)),
        "kurt": float(sp_stats.kurtosis(x)),
    }
    f, p = sp_signal.welch(x, fs=fs, nperseg=min(len(x), int(8 * fs)))
    pn = p / p.sum()
    out["peak_hz"] = float(f[np.argmax(p)])
    out["centroid_hz"] = float(np.sum(f * pn))
    out["spectral_entropy"] = float(
        -np.sum(pn * np.log2(pn + 1e-20)) / np.log2(len(pn))
    )

    coeffs = pywt.wavedec(x - np.mean(x), DWT_WAVELET, level=DWT_LEVEL)
    names = [f"a{DWT_LEVEL}", *(f"d{DWT_LEVEL - i}" for i in range(DWT_LEVEL))]
    energy = np.array([np.sum(c**2) for c in coeffs])
    for name, c, e in zip(names, coeffs, energy, strict=True):
        q = c**2 / e if e > 0 else np.zeros_like(c)
        out[f"dwt_{name}_rel_energy"] = float(e / energy.sum())
        out[f"dwt_{name}_entropy"] = float(-np.sum(q * np.log2(q + 1e-20)))

    emd = EMD()
    emd.emd(x - np.mean(x), max_imf=N_IMFS)
    imfs, res = emd.get_imfs_and_residue()
    total = np.sum(imfs**2) + np.sum(res**2)
    for i, imf in enumerate(imfs[:N_IMFS]):
        phase = np.unwrap(np.angle(sp_signal.hilbert(imf)))
        out[f"imf{i + 1}_rel_energy"] = float(np.sum(imf**2) / total)
        out[f"imf{i + 1}_mean_freq_hz"] = float(
            np.mean(np.diff(phase)) * fs / (2 * np.pi)
        )
    return out


def _longest_run(sig: Signal, a: pd.Timestamp, b: pd.Timestamp) -> np.ndarray:
    m = (sig.t >= a) & (sig.t < b)
    x, t = sig.x[m], sig.t[m]
    if len(x) < 2:
        return x
    secs = (t - t[0]).total_seconds().to_numpy()
    seg = max(split_segments(secs, sig.fs), key=lambda s: s.stop - s.start)
    return x[seg]


def _stats(x: pd.Series) -> dict[str, float]:
    if len(x) < 4:
        return {}
    return {
        "mean": float(x.mean()),
        "sd": float(x.std()),
        "skew": float(sp_stats.skew(x)),
        "kurt": float(sp_stats.kurtosis(x)),
    }


# --- Session -------------------------------------------------------------------


def _magnitude(
    session_dir: Path, meta: dict[str, Any], device: str, stream: str
) -> pd.Series:
    path, anchor = stream_source(session_dir, meta, device, stream)
    if not path.exists() or anchor is None:
        return pd.Series(dtype=float)
    df = _read_stream_csv(path, stream)
    col = "ACC_Mag_mG" if stream == "acc" else "GYRO_Mag_dps"
    if col not in df:
        return pd.Series(dtype=float)
    return pd.Series(df[col].to_numpy(float), index=_to_host(anchor, df["Timestamp_s"]))


def load_signals(session_dir: Path | str) -> SessionSignals:
    """Load every stream feature extraction uses (dual or single-device session)."""
    session_dir = Path(session_dir)
    meta = _read_meta(session_dir)
    out = SessionSignals()
    out.ecg, out.ecg_beats, out.ecg_templates = load_ecg(session_dir, meta)
    out.ecg_fs = out.ecg.fs if out.ecg else float("nan")

    rr = load_h10_beats(session_dir, meta)
    if len(rr):
        out.intervals["rr"] = rr.rename(columns={"rr_ms": "ms"})
    ppi = load_sense_ppi(session_dir, meta)
    if len(ppi):
        out.intervals["ppi"] = ppi[["t", "ppi_ms"]].rename(columns={"ppi_ms": "ms"})
    beats, filt, ppg_t, fs = load_ppg_channels(session_dir, meta)
    out.ppg = {ch: Signal(x, ppg_t, fs) for ch, x in filt.items()}
    if beats:
        # ponytail: one PPG channel per session (most valid beats); per-window choice if it matters
        best = max(beats, key=lambda ch: int(_valid(_seq(beats[ch]["ibi_ms"])).sum()))
        out.intervals["ppgbeat"] = beats[best].rename(columns={"ibi_ms": "ms"})

    for name, device, stream in (
        ("h10_acc", "h10", "acc"),
        ("sense_acc", "sense", "acc"),
        ("sense_gyro", "sense", "gyro"),
    ):
        mag = _magnitude(session_dir, meta, device, stream)
        if len(mag):
            out.imu[name] = mag
    out.h10_motion = load_motion(session_dir, meta, "h10")
    return out


def _seq(values: pd.Series) -> list[float | None]:
    return [None if pd.isna(v) else float(v) for v in values]


def _extent(sig: SessionSignals) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    spans = [(d["t"].min(), d["t"].max()) for d in sig.intervals.values() if len(d)]
    spans += [(s.t.min(), s.t.max()) for s in sig.ppg.values() if len(s.t)]
    if sig.ecg is not None:
        spans.append((sig.ecg.t.min(), sig.ecg.t.max()))
    if not spans:
        return None
    return max(a for a, _ in spans).ceil("1s"), min(b for _, b in spans)


def extract_features(
    session_dir: Path | str,
    window_s: int = WINDOW_S,
    starts: pd.Series | None = None,
    signals: SessionSignals | None = None,
) -> pd.DataFrame:
    """One feature row per window; see the module docstring for the columns.

    ``starts`` reuses an existing window grid (e.g. ``build_windows(...)["start"]``);
    otherwise windows tile the span where all recorded streams overlap.
    ``signals`` reuses an already loaded :func:`load_signals` result.
    """
    sig = signals or load_signals(session_dir)
    win = pd.Timedelta(window_s, "s")
    if starts is None:
        span = _extent(sig)
        if span is None:
            return pd.DataFrame()
        starts = pd.Series(pd.date_range(span[0], span[1] - win, freq=win))
    long = pd.Timedelta(LONG_WINDOW_S, "s")

    rows = []
    for a in starts:
        b = a + win
        row: dict[str, Any] = {"start": a}

        m = sig.h10_motion[(sig.h10_motion.index >= a) & (sig.h10_motion.index < b)]
        motion = float((m > MOTION_SD_MG).mean()) if len(m) else 0.0
        if not sig.ecg_beats.empty:
            in_win = ((sig.ecg_beats["t"] >= a) & (sig.ecg_beats["t"] < b)).to_numpy()
            row.update(
                ecg_window_features(
                    sig.ecg_beats[in_win], sig.ecg_templates[in_win], motion
                )
            )
        if sig.ecg is not None:
            feats = signal_features(_longest_run(sig.ecg, a, b), sig.ecg.fs)
            row.update({f"ecg_{k}": v for k, v in feats.items()})

        for src, d in sig.intervals.items():
            w = d[(d["t"] >= a) & (d["t"] < b)]
            row.update({f"{src}_{k}": v for k, v in hrv_short(_seq(w["ms"])).items()})
            lo, hi = d["t"].min(), d["t"].max()
            a5 = min(max(a + win / 2 - long / 2, lo), max(hi - long, lo))
            w5 = d[(d["t"] >= a5) & (d["t"] < a5 + long)]
            t5 = (w5["t"] - a5).dt.total_seconds().to_numpy()
            row.update(
                {f"{src}_{k}": v for k, v in hrv_long(t5, _seq(w5["ms"])).items()}
            )

        if sig.ppg:
            runs = {ch: _longest_run(s, a, b) for ch, s in sig.ppg.items()}
            fs = next(iter(sig.ppg.values())).fs
            sqi = {ch: spectral_sqi(x, fs) for ch, x in runs.items()}
            best = max(sqi, key=lambda ch: -1.0 if np.isnan(sqi[ch]) else sqi[ch])
            row["ppg_channel"] = best
            row.update(
                {f"ppg_{k}": v for k, v in signal_features(runs[best], fs).items()}
            )

        for name, mag in sig.imu.items():
            w = mag[(mag.index >= a) & (mag.index < b)]
            row.update({f"{name}_{k}": v for k, v in _stats(w).items()})
        rows.append(row)
    return pd.DataFrame(rows)
