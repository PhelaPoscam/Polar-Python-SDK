"""Unit tests for CSV and JSON exporters."""

import json
import tempfile
from pathlib import Path

from awe_polar.connector.exporters.csv_sink import CsvSink
from awe_polar.connector.exporters.json_sink import JsonLinesSink
from awe_polar.connector.schemas import SignalPacket


class TestCsvSink:
    def test_csv_writes_header_and_row(self):
        p = SignalPacket(
            timestamp=1000.0, source="h10", subject_id="s1",
            signals={"hr": 72}, features={"rmssd": 40.0},
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.csv"
            sink = CsvSink(path)
            sink.send(p)
            sink.send(p)

            lines = path.read_text().strip().splitlines()
            assert len(lines) == 3  # header + 2 rows
            assert "timestamp" in lines[0].lower()
            assert "signals.hr" in lines[0]

    def test_csv_send_dict(self):
        payload = {"timestamp": 1.0, "source": "x", "signals": {"a": 1}}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "d.csv"
            CsvSink(path).send(payload)
            content = path.read_text()
            assert "1.0" in content
            assert "signals.a" in content


class TestJsonLinesSink:
    def test_json_writes_one_line_per_packet(self):
        p = SignalPacket(source="h10", signals={"hr": 80})
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "out.jsonl"
            sink = JsonLinesSink(path)
            sink.send(p)
            sink.send(p)

            lines = path.read_text().strip().splitlines()
            assert len(lines) == 2
            obj = json.loads(lines[0])
            assert obj["source"] == "h10"
            assert obj["signals"]["hr"] == 80

    def test_json_send_dict(self):
        payload = {"source": "test", "signals": {"x": 1}, "features": {}}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "d.jsonl"
            JsonLinesSink(path).send(payload)
            obj = json.loads(path.read_text().strip())
            assert obj["source"] == "test"
