"""Unit tests for optical PPG signal processing and beat detection."""

from __future__ import annotations

import numpy as np
import pytest

from polar_ble_sdk.research.ppg import (
    bandpass_filter,
    beat_intervals,
    detect_beats,
    spectral_hr,
    spectral_sqi,
    split_segments,
)


def pulse_wave(beats: np.ndarray, t: np.ndarray, width: float = 0.08) -> np.ndarray:
    return np.sum(np.exp(-0.5 * ((t[:, None] - beats[None, :]) / width) ** 2), axis=1)


class TestPpgSignalProcessing:
    def test_spectral_hr(self) -> None:
        fs = 55.0
        t = np.arange(0, 30, 1 / fs)
        wave = np.sin(2 * np.pi * 1.2 * t) + 0.3 * np.sin(2 * np.pi * 2.4 * t)
        assert spectral_hr(wave, fs) == pytest.approx(72.0, abs=1.0)

    def test_spectral_hr_prefers_fundamental_over_strong_harmonic(self) -> None:
        fs = 100.0
        t = np.arange(0, 30, 1 / fs)
        wave = 0.8 * np.sin(2 * np.pi * 1.0 * t) + np.sin(2 * np.pi * 2.0 * t)
        assert spectral_hr(wave, fs) == pytest.approx(60.0, abs=1.5)

    def test_beats_are_subsample_precise(self) -> None:
        """At 55 Hz a bare sample index would be off by up to 9 ms."""
        fs = 55.0
        true_beats = np.cumsum(np.full(30, 0.8537))
        t = np.arange(0, true_beats[-1] + 1, 1 / fs)
        x = bandpass_filter(pulse_wave(true_beats, t), fs)
        found = detect_beats(x, t, fs)
        ibi = np.diff(found) * 1000
        assert np.std(ibi[2:-2]) < 3.0  # true IBI is constant
        assert np.mean(ibi[2:-2]) == pytest.approx(853.7, abs=1.0)

    def test_no_interval_spans_a_gap(self) -> None:
        fs = 100.0
        beats = np.cumsum(np.full(40, 0.8))
        t = np.arange(0, beats[-1] + 1, 1 / fs)
        keep = (t < 12) | (t > 15)  # 3 s of lost packets
        t, x = t[keep], pulse_wave(beats, t)[keep]
        segs = split_segments(t, fs)
        assert len(segs) == 2
        by_seg = [(bandpass_filter(x[s], fs), t[s]) for s in segs]
        _, ibi = beat_intervals(by_seg, fs)
        assert None in ibi
        assert max(v for v in ibi if v is not None) < 900

    def test_sqi_separates_clean_pulse_from_noise(self) -> None:
        fs = 135.0
        t = np.arange(0, 60, 1 / fs)
        clean = bandpass_filter(pulse_wave(np.arange(0.5, 60, 0.9), t), fs)
        noise = bandpass_filter(np.random.default_rng(0).normal(size=len(t)), fs)
        assert spectral_sqi(clean, fs) > 0.5
        assert spectral_sqi(noise, fs) < 0.3
