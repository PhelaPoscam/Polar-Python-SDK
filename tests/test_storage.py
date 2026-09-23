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

    def test_stream_frame_logger_flushes_multi_sample_frames(self, tmp_path: Path):
        ecg_file = tmp_path / "ecg.csv"
        logger = StreamFrameLogger(ecg_file, "ecg")
        logger.open()
        for i in range(2):  # 146 samples: never a multiple of 100
            logger.write_frame(i * 500_000_000, list(range(73)))
        assert len(ecg_file.read_text(encoding="utf-8").splitlines()) == 3
        logger.close()

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
        rate_tracker.track("ecg", 130, timestamp=1.0)
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
        assert "clock_zero_points" in data
        assert "host_epoch_ns" in data["clock_zero_points"]
        assert data["host_epoch_start_ns"] > 0

    def test_session_base_dir_ending_in_data_does_not_nest(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        mgr = SessionManager(
            base_dir=data_dir, device_type="dual", session_id="test_dual", is_dual=True
        )
        assert mgr.session_dir == data_dir / "dual" / "test_dual"

    def test_session_dir_uses_base_dir_as_data_root(self, tmp_path: Path):
        root = tmp_path / "Recordings"
        mgr = SessionManager(base_dir=root, device_type="h10", session_id="s1")
        assert mgr.session_dir == root / "h10" / "s1"

    def test_close_all_saves_once_and_can_keep_the_log_open(self, tmp_path: Path):
        mgr = SessionManager(base_dir=tmp_path, device_type="h10", session_id="s1")
        mgr.init_event_log()
        mgr.close_all(keep_log=True)  # saved before the BLE teardown
        meta = mgr.session_dir / "session_meta.json"
        first = meta.read_text(encoding="utf-8")
        assert mgr.log_file is not None  # teardown messages still get logged
        mgr.register_marker("late")
        mgr.close_all()  # e.g. the console-close handler firing as well
        assert meta.read_text(encoding="utf-8") == first
        assert mgr.log_file is None

    def test_untimestamped_ppi_gets_host_anchor_and_beat_times(self, tmp_path: Path):
        """Verity Sense PPI frames carry timestamp 0: cumulative clock, host-anchored."""
        mgr = SessionManager(base_dir=tmp_path, device_type="dual", session_id="s")
        fl = mgr.create_frame_logger("ppi", sub_device="sense")
        fl.write_ppi_frames([(0, 800, 10, 75, 1, 1, 0), (0, 900, 10, 70, 1, 1, 0)])
        fl.write_ppi_frames([(0, 850, 10, 72, 1, 1, 1)])
        mgr.close_all()
        rows = fl.path.read_text(encoding="utf-8").splitlines()
        # Each row is stamped at its beat; the first frame's last beat is t=0
        assert [r.split(",")[0] for r in rows[1:]] == ["-0.900", "0.000", "0.850"]
        assert rows[3].endswith(",1")  # Invalid flag kept
        meta = json.loads((mgr.session_dir / "session_meta.json").read_text("utf-8"))
        assert "sense_ppi_host_epoch_ns" in meta["clock_zero_points"]
