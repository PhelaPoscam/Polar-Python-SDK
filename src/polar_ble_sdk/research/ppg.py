"""PPG signal processing: filtering, beat detection and signal quality for Verity Sense PPG.

Beats are the maxima of the band-passed pulse wave, refined to sub-sample
precision with parabolic interpolation: at 55 Hz a bare sample index quantises
each beat to 18 ms, which adds ~13 ms of noise to RMSSD. Gaps in the sample
stream (lost BLE packets) split the signal into segments that are filtered and
searched separately, so no inter-beat interval ever spans a gap.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import signal as sp_signal

HR_MIN_BPM = 30.0
HR_MAX_BPM = 240.0
BANDPASS = (0.5, 4.0)  # Hz ~ 30-240 BPM
PEAK_MIN_DIST_S = 0.25  # 240 BPM
PEAK_MIN_PROMINENCE_SD = 1.0  # beat prominence vs local signal SD
MIN_SEGMENT_S = 5.0
GAP_FACTOR = 3.0  # a sample spacing > 3x nominal is a gap


def bandpass_filter(
    x: np.ndarray, fs: float, lo: float = BANDPASS[0], hi: float = BANDPASS[1]
) -> np.ndarray:
    """Zero-phase Butterworth band-pass for the physiological HR frequency range."""
    if fs <= 0 or len(x) < 16:
        return x
    nyq = fs / 2.0
    if nyq <= lo or hi <= lo:
        return x
    lo = min(max(lo, 0.01), nyq * 0.95)
    hi = min(max(hi, lo + 0.05), nyq * 0.95)
    if hi <= lo:
        return x
    b, a = sp_signal.butter(2, [lo, hi], btype="band", fs=fs)
    return sp_signal.filtfilt(b, a, x)


def estimate_fs(t_s: np.ndarray) -> float:
    """Nominal sampling rate from the median sample spacing."""
    dt = np.diff(t_s)
    dt = dt[dt > 0]
    return float(1.0 / np.median(dt)) if len(dt) else float("nan")


def split_segments(t_s: np.ndarray, fs: float) -> list[slice]:
    """Contiguous runs of samples, split wherever the spacing exceeds GAP_FACTOR/fs."""
    breaks = np.flatnonzero(np.diff(t_s) > GAP_FACTOR / fs) + 1
    edges = np.concatenate(([0], breaks, [len(t_s)]))
    return [slice(int(a), int(b)) for a, b in zip(edges[:-1], edges[1:], strict=True)]


def detect_beats(x: np.ndarray, t_s: np.ndarray, fs: float) -> np.ndarray:
    """Sub-sample beat times (s) in one contiguous, band-passed segment."""
    if len(x) < int(MIN_SEGMENT_S * fs):
        return np.array([], dtype=float)
    pk, props = sp_signal.find_peaks(
        x, distance=max(int(PEAK_MIN_DIST_S * fs), 1), prominence=0
    )
    win = max(int(5 * fs), 3)
    local_sd = pd.Series(x).rolling(win, center=True, min_periods=1).std().to_numpy()
    pk = pk[props["prominences"] >= PEAK_MIN_PROMINENCE_SD * local_sd[pk]]
    pk = pk[(pk > 0) & (pk < len(x) - 1)]
    y0, y1, y2 = x[pk - 1], x[pk], x[pk + 1]
    denom = y0 - 2 * y1 + y2
    delta = np.where(denom != 0, 0.5 * (y0 - y2) / np.where(denom != 0, denom, 1), 0.0)
    delta = np.clip(delta, -0.5, 0.5)
    return t_s[pk] + delta * (1.0 / fs)


def beat_intervals(
    signal_by_segment: list[tuple[np.ndarray, np.ndarray]], fs: float
) -> tuple[list[float], list[float | None]]:
    """Beat times and inter-beat intervals (ms), with ``None`` at every gap.

    ``times[i]`` is the time of the beat that ends ``ibi[i]``.
    """
    times: list[float] = []
    ibi: list[float | None] = []
    for x, t in signal_by_segment:
        beats = detect_beats(x, t, fs)
        if len(beats) < 2:
            continue
        if ibi:
            times.append(float(beats[0]))
            ibi.append(None)  # not adjacent to the previous segment's last beat
        times.extend(beats[1:].tolist())
        ibi.extend((np.diff(beats) * 1000.0).tolist())
    return times, ibi


def spectral_hr(x: np.ndarray, fs: float) -> float:
    """HR (BPM) at the Welch PSD peak, with a check for a dominant 2nd/3rd harmonic."""
    if len(x) < 64 or fs <= 0:
        return float("nan")
    nfft = max(4096, 8 * len(x))
    nperseg = min(len(x), max(256, int(8.0 * fs)))
    freqs, psd = sp_signal.welch(x, fs=fs, nperseg=nperseg, nfft=nfft)
    band = (freqs >= HR_MIN_BPM / 60.0) & (freqs <= HR_MAX_BPM / 60.0)
    if band.sum() == 0:
        return float("nan")
    f = freqs[band]
    p = psd[band]
    i_peak = int(np.argmax(p))
    if 0 < i_peak < len(p) - 1:
        denom = p[i_peak - 1] - 2 * p[i_peak] + p[i_peak + 1]
        delta = 0.5 * (p[i_peak - 1] - p[i_peak + 1]) / denom if denom != 0 else 0.0
        f_peak = f[i_peak] + delta * (f[1] - f[0])
    else:
        f_peak = f[i_peak]

    peaks, _ = sp_signal.find_peaks(p, height=0.6 * p[i_peak])
    for pk in peaks:
        if pk != i_peak and f[pk] < f_peak:
            ratio = f_peak / f[pk]
            if any(abs(ratio - k) < 0.1 for k in (2.0, 3.0)):
                f_peak = f[pk]
                break

    hr = f_peak * 60.0
    return float(hr) if HR_MIN_BPM <= hr <= HR_MAX_BPM else float("nan")


def spectral_sqi(x: np.ndarray, fs: float) -> float:
    """Signal quality 0..1: share of in-band power at the pulse fundamental and 2nd harmonic.

    A clean pulse wave concentrates its power there; motion spreads it out.
    Uses only the PPG itself, never the reference device.
    """
    if len(x) < 64 or fs <= 0:
        return float("nan")
    nperseg = min(len(x), max(256, int(8.0 * fs)))
    freqs, psd = sp_signal.welch(x, fs=fs, nperseg=nperseg, nfft=max(4096, 8 * len(x)))
    band = (freqs >= BANDPASS[0]) & (freqs <= BANDPASS[1])
    total = psd[band].sum()
    if total <= 0:
        return float("nan")
    f0 = freqs[band][int(np.argmax(psd[band]))]
    near = (np.abs(freqs - f0) <= 0.1) | (np.abs(freqs - 2 * f0) <= 0.1)
    return float(psd[band & near].sum() / total)
