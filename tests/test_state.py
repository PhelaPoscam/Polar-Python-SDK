"""Unit tests for in-memory device state feeds."""

import math

import pytest

from polar_ble_sdk.metrics.hrv import calculate_rmssd
from polar_ble_sdk.metrics.rate_tracker import RateTracker
from polar_ble_sdk.session.state import (
    feed_hr,
    feed_ppi,
    make_device_state,
)


class TestFeedPpiFeedsRrHistory:
    """The Sense HR stream carries empty RR lists; PPI is the isolated interval source."""

    def _make_state(self):
        return make_device_state("test"), RateTracker()

    def test_ppi_populates_rr_history_and_intervals(self):
        st, ts = self._make_state()
        feed_ppi(
            [(1_000_000_000, 850.0), (1_000_850_000, 860.0), (1_001_710_000, 870.0)],
            st,
            ts,
        )
        assert st["ppi_count"] == 3
        assert len(st["ppi_history"]) == 3
        assert st["ppi_intervals"][-1] == 870.0

    def test_ppi_feeds_rmssd(self):
        st, ts = self._make_state()
        feed_ppi(
            [(1_000_000_000, 850.0), (1_000_850_000, 860.0), (1_001_710_000, 870.0)],
            st,
            ts,
        )
        # RMSSD of 850/860/870 ms: sqrt(mean((10)^2+(10)^2)) = 10 ms
        assert calculate_rmssd(st["ppi_history"]) == pytest.approx(10.0, abs=0.01)

    def test_ppi_ignores_invalid_zero_intervals(self):
        st, ts = self._make_state()
        feed_ppi([(1_000_000_000, 0.0), (1_000_850_000, 850.0)], st, ts)
        # The invalid interval stays as a gap marker so RMSSD won't bridge it
        assert list(st["ppi_history"]) == [None, 850.0]
        assert st["ppi_intervals"] == [850.0]

    def test_ppi_flagged_invalid_breaks_adjacency(self):
        st, ts = self._make_state()
        ok = (0, 800.0, 10, 75, True, True, False)
        bad = (0, 1200.0, 10, 75, True, True, True)
        feed_ppi([ok, (0, 810.0, 10, 75, True, True, False), bad, ok], st, ts)
        assert list(st["ppi_history"]) == [800.0, 810.0, None, 800.0]

    def test_hr_stream_with_empty_rr_leaves_rmssd_nan(self):
        """Regression: the Sense sends HR with empty RR — RMSSD must be NaN."""
        st, ts = self._make_state()
        feed_hr((73, []), st)
        assert len(st["rr_history"]) == 0
        assert math.isnan(calculate_rmssd(st["rr_history"]))

    def test_sense_interval_selection_prefers_ppi_over_empty_rr(self):
        """Sense receives empty RR from HR stream and intervals from PPI stream."""
        st, ts = self._make_state()
        feed_hr((73, []), st)
        feed_ppi(
            [(1_000_000_000, 800.0), (1_000_800_000, 820.0), (1_001_620_000, 840.0)],
            st,
            ts,
        )
        intervals = st["ppi_history"] if st["ppi_history"] else st["rr_history"]
        assert len(intervals) == 3
        assert calculate_rmssd(intervals) == pytest.approx(20.0, abs=0.01)
