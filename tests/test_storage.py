"""Unit tests for storage utilities, frame loggers, and session managers."""

import json
from pathlib import Path

from polar_ble_sdk.metrics.rate_tracker import RateTracker
from polar_ble_sdk.session.session import DeviceMetadata, SessionManager
from polar_ble_sdk.storage.frame_logger import StreamFrameLogger
from polar_ble_sdk.storage.summary_logger import CsvLogger


class TestStorageLoggers:
    def test_csv_logger_write_header_and_rows(self, tmp_path: Path):
        csv_file = tmp_path / "test_summary.csv"
        logger = CsvLogger(csv_file, ["Timestamp", "HeartRate", "RMSSD"])
        logger.write_header()
        logger.write_row(["2026-08-18 12:00:00", 72, 45.2])
        logger.write_row(["2026-08-18 12:00:01", 73, 44.8])

        assert csv_file.exists()
        lines = csv_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        assert lines[0] == "Timestamp,HeartRate,RMSSD"
        assert "72,45.2" in lines[1]
        assert logger.rows_written == 2

    def test_stream_frame_logger_ecg(self, tmp_path: Path):
        ecg_file = tmp_path / "ecg.csv"
        logger = StreamFrameLogger(ecg_file, "ecg")
        logger.open()
        # write 2 frames: 1000ns relative start, data = [100, 200]
        logger.write_frame(1_000_000_000, [100, 200])
        logger.write_frame(1_500_000_000, [300, 400])
        logger.close()

        lines = ecg_file.read_text(encoding="utf-8").strip().splitlines()
        assert lines[0] == "Timestamp_s,uV_Samples"
        assert lines[1] == "0.000,100,200"
        assert lines[2] == "0.500,300,400"

    def test_stream_frame_logger_hr(self, tmp_path: Path):
        hr_file = tmp_path / "hr.csv"
        logger = StreamFrameLogger(hr_file, "hr")
        logger.open()
        logger.write_frame(1_000_000_000, (70, [850.0, 860.0]))
        logger.close()

        lines = hr_file.read_text(encoding="utf-8").strip().splitlines()
        assert lines[0] == "Timestamp_s,HeartRate_BPM,RR_Intervals_ms"
        assert lines[1] == "0.000,70,850.0;860.0"


class TestSessionManager:
    def test_session_creation_and_manifest_serialization(self, tmp_path: Path):
        mgr = SessionManager(
            base_dir=tmp_path,
            device_type="h10",
            session_id="20260818_test",
        )
        mgr.init_event_log(prefix="monitor")
        mgr.metadata.devices["h10"] = DeviceMetadata(
            name="Polar H10 Test",
            address="AA:BB:CC:DD:EE:FF",
            device_type="h10",
            battery_start="90%",
            battery_end="89%",
        )
        mgr.register_marker("baseline_start", timestamp_s=100.0)

        rate_tracker = RateTracker()
        rate_tracker.track("ecg", 130, timestamp=0.0)
        rate_tracker.track("ecg", 130, timestamp=2.0)

        mgr.close_all(rate_tracker=rate_tracker, configured_rates={"ecg": 130})

        meta_path = mgr.session_dir / "session_meta.json"
        assert meta_path.exists()

        data = json.loads(meta_path.read_text(encoding="utf-8"))
        assert data["session_id"] == "20260818_test"
        assert data["session_type"] == "single"
        assert data["devices"]["h10"]["address"] == "AA:BB:CC:DD:EE:FF"
        assert len(data["markers"]) == 1
        assert data["markers"][0]["label"] == "baseline_start"
        assert "ecg" in data["stream_results"]
        assert data["stream_results"]["ecg"]["observed_hz"] == 130.0
