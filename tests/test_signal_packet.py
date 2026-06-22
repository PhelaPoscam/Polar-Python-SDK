"""Unit tests for SignalPacket — the central data contract."""

import json

from polar_ble_sdk.connector.schemas import SignalPacket


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
