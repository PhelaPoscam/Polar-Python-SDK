import math

import pytest

from polar_ble_sdk.metrics.hrv import (
    calculate_pnn50,
    calculate_rmssd,
    calculate_sdnn,
    rr_valid_mask,
    successive_differences,
)
from polar_ble_sdk.metrics.rate_tracker import (
    RateTracker,
    StreamAccumulator,
)


class TestHrvCalculations:
    def test_rmssd_standard_sequence(self):
        # Intervals: 800, 810, 830 ms
        # Differences: +10, +20 ms -> Squared: 100, 400 -> Mean: 250 -> Sqrt: 15.811 ms
        rr = [800.0, 810.0, 830.0]
        rmssd = calculate_rmssd(rr)
        assert rmssd == pytest.approx(15.811388, rel=1e-4)

    def test_rmssd_empty_and_single(self):
        assert math.isnan(calculate_rmssd([]))
        assert math.isnan(calculate_rmssd([800.0]))

    def test_rmssd_never_differences_across_a_gap(self):
        # 800 and 820 are not adjacent (a missing beat sits between them)
        assert math.isnan(calculate_rmssd([0.0, 800.0, None, 820.0, -10.0]))
        assert calculate_rmssd([800.0, 810.0, None, 820.0, 840.0]) == pytest.approx(
            math.sqrt((10**2 + 20**2) / 2)
        )

    def test_ectopic_beat_is_excluded_not_differenced(self):
        # A premature beat (500) followed by a compensatory pause (1100)
        rr = [800.0, 810.0, 800.0, 805.0, 500.0, 1100.0, 800.0, 810.0, 805.0, 800.0]
        diffs = successive_differences(rr)
        assert all(abs(d) <= 10 for d in diffs)
        assert rr_valid_mask(rr)[4:6] == [False, False]

    def test_sdnn_standard_sequence(self):
        # Intervals: 800, 820, 840 ms -> Mean: 820 -> Variance: (( -20)^2 + 0 + 20^2)/2 = 400 -> SD: 20 ms
        rr = [800.0, 820.0, 840.0]
        assert calculate_sdnn(rr) == pytest.approx(20.0, rel=1e-4)

    def test_pnn50_calculation(self):
        # Intervals: 800, 860 (+60 > 50), 880 (+20 <= 50) -> 1 of 2 diffs > 50 ms -> 50%
        rr = [800.0, 860.0, 880.0]
        assert calculate_pnn50(rr) == pytest.approx(50.0, rel=1e-4)


class TestRateTracker:
    def test_accumulator_and_average_hz(self):
        acc = StreamAccumulator()
        acc.add(130, timestamp=100.0)
        acc.add(130, timestamp=101.0)
        assert acc.samples == 260
        assert acc.duration == pytest.approx(1.0)
        # The first batch's samples predate first_ts: 130 samples over 1 s.
        assert acc.average_hz == pytest.approx(130.0)

    def test_sliding_window_rate_tracker(self):
        tracker = RateTracker(sliding_window_s=1.5)
        tracker.track("ecg", 65, timestamp=10.0)
        tracker.track("ecg", 65, timestamp=10.5)
        tracker.track("ecg", 65, timestamp=11.0)

        # Batches at 10.5 and 11.0 carry 130 samples over 1.0 s -> 130 Hz
        hz = tracker.get_instantaneous_hz("ecg", now=11.2)
        assert hz == pytest.approx(130.0, rel=1e-2)

    def test_verify_all(self):
        tracker = RateTracker()
        tracker.track("ecg", 130, timestamp=0.0)
        tracker.track("ecg", 130, timestamp=1.0)
        tracker.track("ecg", 130, timestamp=2.0)  # 260 samples after t=0 over 2s

        results = tracker.verify_all({"ecg": 130})
        assert len(results) == 1
        assert results[0].stream == "ecg"
        assert results[0].observed_hz == pytest.approx(130.0)
        assert results[0].is_match is True
