"""Unit tests for SignalPacket — the central data contract."""

import json
from collections import deque

import pytest

from polar_ble_sdk.connector.schemas import SignalPacket
from polar_ble_sdk.dashboard_utils import (
    calculate_rmssd,
    feed_hr,
    feed_ppi,
    make_device_state,
)


class TestSignalPacket:
    def test_defaults(self):
        p = SignalPacket()
        assert p.source == "unknown"
        assert p.subject_id is None
        assert p.signals == {}
        assert p.features == {}

    def test_explicit_fields(self):
        p = SignalPacket(
            timestamp=123.456,
            source="h10",
            subject_id="subj-1",
            signals={"hr_bpm": 72},
            features={"rmssd": 42.0},
        )
        assert p.timestamp == 123.456
        assert p.source == "h10"
        assert p.subject_id == "subj-1"
        assert p.signals["hr_bpm"] == 72

    def test_to_dict_roundtrip(self):
        p = SignalPacket(source="sense", signals={"ppg": 100}, features={"stress": 0.7})
        d = p.to_dict()
        assert d["source"] == "sense"
        assert d["signals"]["ppg"] == 100
        assert d["features"]["stress"] == 0.7
        # keys are plain dicts, not the same object
        assert d["signals"] is not p.signals

    def test_to_dict_preserves_timestamp(self):
        p = SignalPacket(timestamp=999.0)
        assert p.to_dict()["timestamp"] == 999.0

    def test_to_json_compact(self):
        p = SignalPacket(source="h10", signals={"hr": 80})
        js = p.to_json()
        assert '"source":"h10"' in js
        assert '"hr":80' in js
        json.loads(js)  # valid JSON

    def test_default_factory_timestamp_is_float(self):
        p = SignalPacket()
        assert isinstance(p.timestamp, float)
        assert p.timestamp > 0


class TestFeedPpiFeedsRrHistory:
    """The Sense HR stream carries empty RR lists; PPI is the RR source."""

    def _make_state(self):
        return make_device_state("test"), deque(maxlen=20)

    def test_ppi_populates_rr_history_and_intervals(self):
        st, ts = self._make_state()
        feed_ppi(
            [(1_000_000_000, 850.0), (1_000_850_000, 860.0), (1_001_710_000, 870.0)],
            st,
            ts,
        )
        assert st["ppi_count"] == 3
        assert len(st["rr_history"]) == 3
        assert st["rr_intervals"][-1] == 870.0

    def test_ppi_feeds_rmssd(self):
        st, ts = self._make_state()
        feed_ppi(
            [(1_000_000_000, 850.0), (1_000_850_000, 860.0), (1_001_710_000, 870.0)],
            st,
            ts,
        )
        # RMSSD of 850/860/870 ms: sqrt(mean((10)^2+(10)^2)) = 10 ms
        assert calculate_rmssd(st["rr_history"]) == pytest.approx(10.0, abs=0.01)

    def test_ppi_ignores_invalid_zero_intervals(self):
        st, ts = self._make_state()
        feed_ppi([(1_000_000_000, 0.0), (1_000_850_000, 850.0)], st, ts)
        assert len(st["rr_history"]) == 1
        assert st["rr_history"][0] == 850.0

    def test_hr_stream_with_empty_rr_leaves_rmssd_zero(self):
        """Regression: the Sense sends HR with empty RR — RMSSD must be 0."""
        st, ts = self._make_state()
        feed_hr((73, []), st)
        assert len(st["rr_history"]) == 0
        assert calculate_rmssd(st["rr_history"]) == 0.0
