"""Unit tests for optical PPG signal processing and beat detection."""

from __future__ import annotations

import numpy as np
import pytest

from polar_ble_sdk.research.ppg import (
    bandpass_filter,
    clean_ibi,
    epoch_hr_from_fft,
    epoch_hr_from_zc,
    ibi_to_hr,
    ibi_to_rmssd,
    zero_crossing_rate,
)


class TestPpgSignalProcessing:
    def test_zero_crossing_rate(self) -> None:
        fs = 100.0
        # 1 Hz sine wave for 5 seconds -> 10 zero crossings -> rate = 1.0 Hz
        t = np.linspace(0, 5, 500, endpoint=False)
        sin_wave = np.sin(2 * np.pi * 1.0 * t)
        zc = zero_crossing_rate(sin_wave, fs)
        assert pytest.approx(zc, rel=0.05) == 1.0

    def test_epoch_hr_from_zc(self) -> None:
        fs = 100.0
        # 1.2 Hz wave (72 BPM)
        t = np.linspace(0, 10, 1000, endpoint=False)
        wave = np.sin(2 * np.pi * 1.2 * t)
        hr = epoch_hr_from_zc(wave, fs)
        assert pytest.approx(hr, rel=0.05) == 72.0

    def test_epoch_hr_from_fft(self) -> None:
        fs = 55.0
        t = np.linspace(0, 10, int(10 * fs), endpoint=False)
        # 1.5 Hz wave (90 BPM)
        wave = np.sin(2 * np.pi * 1.5 * t)
        hr = epoch_hr_from_fft(wave, fs)
        assert pytest.approx(hr, abs=2.0) == 90.0

    def test_bandpass_filter(self) -> None:
        fs = 100.0
        t = np.linspace(0, 10, 1000, endpoint=False)
        # 1 Hz signal + 20 Hz high frequency noise
        signal = np.sin(2 * np.pi * 1.0 * t) + 0.5 * np.sin(2 * np.pi * 20.0 * t)
        filtered = bandpass_filter(signal, fs, lo=0.5, hi=4.0)
        assert len(filtered) == len(signal)
        # High frequency power should be greatly attenuated
        assert np.std(filtered) < np.std(signal)

    def test_clean_ibi(self) -> None:
        # Standard intervals with one double interval (missed beat)
        ibis = np.array([0.8, 0.82, 1.62, 0.81, 0.79])
        cleaned = clean_ibi(ibis)
        # 1.62 should be split into two ~0.81 intervals
        assert len(cleaned) == 6
        assert all(0.75 <= v <= 0.85 for v in cleaned)

    def test_ibi_to_hr_and_rmssd(self) -> None:
        ibis_s = np.array([0.8, 0.8, 0.8, 0.8])  # 75 BPM
        assert pytest.approx(ibi_to_hr(ibis_s), 1e-2) == 75.0

        ibis_ms = np.array([800.0, 850.0, 810.0, 860.0])
        rmssd = ibi_to_rmssd(ibis_ms)
        assert rmssd > 0
