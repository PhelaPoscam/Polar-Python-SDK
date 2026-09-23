"""Tests for the Lab Streaming Layer (LSL) bridge and burst unrolling."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from polar_ble_sdk.lsl.bridge import HAS_PYLSL, PolarLSLBridge


@pytest.mark.skipif(not HAS_PYLSL, reason="pylsl is not installed")
class TestPolarLSLBridge:
    """Test suite for PolarLSLBridge with live pylsl library."""

    def test_bridge_creation_default_outlets(self) -> None:
        bridge = PolarLSLBridge(
            h10_id="TEST_H10",
            sense_id="TEST_SENSE",
            enable_h10=True,
            enable_sense=True,
            enable_sense_gyro=False,
            enable_sense_mag=False,
            ppg_rate=135.0,
        )
        try:
            assert "h10_ecg" in bridge.outlets
            assert "h10_acc" in bridge.outlets
            assert "h10_hr" in bridge.outlets
            assert "sense_ppg" in bridge.outlets
            assert "sense_acc" in bridge.outlets
            assert "sense_gyro" not in bridge.outlets
            assert "sense_mag" not in bridge.outlets
            assert "markers" in bridge.outlets

            # Verify outlet config channels
            assert bridge.configs["h10_ecg"].channel_count == 1
            assert bridge.configs["h10_acc"].channel_count == 3
            assert bridge.configs["h10_hr"].channel_count == 2
            assert bridge.configs["sense_ppg"].channel_count == 4
            assert bridge.configs["sense_acc"].channel_count == 3
            assert bridge.configs["markers"].channel_count == 1
        finally:
            bridge.close()

    def test_bridge_creation_with_gyro_and_mag(self) -> None:
        bridge = PolarLSLBridge(
            enable_h10=False,
            enable_sense=True,
            enable_sense_gyro=True,
            enable_sense_mag=True,
        )
        try:
            assert "h10_ecg" not in bridge.outlets
            assert "sense_gyro" in bridge.outlets
            assert "sense_mag" in bridge.outlets
            assert bridge.configs["sense_gyro"].nominal_srate == 52.0
            assert bridge.configs["sense_mag"].nominal_srate == 20.0
        finally:
            bridge.close()

    def test_burst_unrolling_ecg(self) -> None:
        bridge = PolarLSLBridge(enable_sense=False)
        mock_outlet = MagicMock()
        bridge.outlets["h10_ecg"] = mock_outlet

        # Simulate 14 ECG microvolt samples arriving from BLE
        samples = [-120.5, -115.0, -80.2, 50.0, 320.0, -90.0, -100.0] * 2
        assert len(samples) == 14
        bridge.push_h10_ecg((1788250000000000000, samples))

        mock_outlet.push_chunk.assert_called_once()
        chunk, timestamps = mock_outlet.push_chunk.call_args[0]

        # Verify chunk structure
        assert len(chunk) == 14
        assert chunk[0] == [-120.5]
        assert chunk[4] == [320.0]

        # Verify timestamp unrolling: strictly monotonic with dt ~= 1/130
        assert len(timestamps) == 14
        for i in range(1, len(timestamps)):
            dt = timestamps[i] - timestamps[i - 1]
            assert pytest.approx(dt, abs=1e-5) == 1.0 / 130.0
            assert timestamps[i] > timestamps[i - 1]

        bridge.close()

    def test_burst_unrolling_ppg(self) -> None:
        bridge = PolarLSLBridge(enable_h10=False, ppg_rate=135.0)
        mock_outlet = MagicMock()
        bridge.outlets["sense_ppg"] = mock_outlet

        # Simulate Verity Sense 4-channel PPG samples
        samples = [
            [-50000, -48000, -49000, -68000],
            [-50100, -48100, -49050, -68050],
            [-50200, -48200, -49100, -68100],
        ]
        bridge.push_sense_ppg((1788250000000000000, samples))

        mock_outlet.push_chunk.assert_called_once()
        chunk, timestamps = mock_outlet.push_chunk.call_args[0]

        assert len(chunk) == 3
        assert chunk[0] == [-50000, -48000, -49000, -68000]
        assert len(timestamps) == 3
        dt = timestamps[1] - timestamps[0]
        assert pytest.approx(dt, abs=1e-5) == 1.0 / 135.0

        bridge.close()

    def test_push_hr(self) -> None:
        bridge = PolarLSLBridge(enable_sense=False)
        mock_outlet = MagicMock()
        bridge.outlets["h10_hr"] = mock_outlet

        bridge.push_h10_hr((84, [714.2]))
        mock_outlet.push_sample.assert_called_once()
        sample, ts = mock_outlet.push_sample.call_args[0]
        assert sample == [84.0, 714.2]
        assert isinstance(ts, float)

        bridge.close()

    def test_push_marker(self) -> None:
        bridge = PolarLSLBridge(enable_h10=False, enable_sense=False)
        mock_outlet = MagicMock()
        bridge.outlets["markers"] = mock_outlet

        bridge.push_marker("stimulus_start")
        mock_outlet.push_sample.assert_called_once()
        sample, ts = mock_outlet.push_sample.call_args[0]
        assert sample == ["stimulus_start"]

        bridge.close()

    def test_wrap_callback(self) -> None:
        bridge = PolarLSLBridge(enable_sense=False)
        recorded: list[Any] = []

        def original_cb(data: Any) -> None:
            recorded.append(data)

        wrapped = bridge.wrap_callback("h10_hr", original_cb)
        wrapped((78, [769.0]))

        assert len(recorded) == 1
        assert recorded[0] == (78, [769.0])
        bridge.close()


def test_lsl_missing_raises_import_error() -> None:
    with (
        patch("polar_ble_sdk.lsl.bridge.HAS_PYLSL", False),
        pytest.raises(ImportError, match="pylsl is required for LSL streaming"),
    ):
        PolarLSLBridge()


def test_burst_clock_learns_device_spacing_and_skips_gaps() -> None:
    from polar_ble_sdk.lsl.bridge import BurstClock

    clock = BurstClock(nominal_hz=200.0)  # flag said 200 Hz, device runs at 52
    dt = 1 / 52
    ts = 10**12
    clock.times(0.0, 10, ts)
    for k in range(1, 20):
        clock.times(0.0, 10, ts + int(k * 10 * dt * 1e9))
    assert clock.dt == pytest.approx(dt, rel=1e-3)
    clock.times(0.0, 10, ts + int(60 * 10 * dt * 1e9))  # 40 frames lost
    assert clock.dt == pytest.approx(dt, rel=1e-3)
    times = clock.times(5.0, 3, ts + int(61 * 10 * dt * 1e9))
    assert times[-1] == 5.0
    assert times[1] - times[0] == pytest.approx(dt, rel=1e-3)
