"""Unit tests for research tools: session data loader and integrity auditor."""

import json
from pathlib import Path

import pytest

from polar_ble_sdk.research.audit import verify_session_integrity
from polar_ble_sdk.research.loader import load_session


@pytest.fixture
def sample_session_dir(tmp_path: Path) -> Path:
    """Create a synthetic single-device session folder structure."""
    session_dir = tmp_path / "data" / "h10" / "20260818_120000"
    raw_dir = session_dir / "raw"
    pp_dir = session_dir / "post-processed"
    raw_dir.mkdir(parents=True)
    pp_dir.mkdir(parents=True)

    # 1. session_meta.json
    meta = {
        "session_id": "20260818_120000",
        "session_type": "single",
        "start_time_iso": "2026-08-18T12:00:00+00:00",
        "devices": {"h10": {"name": "Polar H10", "address": "AA:BB:CC"}},
        "markers": [{"label": "event_1", "timestamp_epoch_s": 10.0}],
    }
    (session_dir / "session_meta.json").write_text(json.dumps(meta), encoding="utf-8")

    # 2. summary.csv
    summary_csv = pp_dir / "summary.csv"
    summary_csv.write_text(
        "Timestamp,HeartRate_BPM,HRV_RMSSD_ms,Battery_Percent\n"
        "2026-08-18 12:00:00,70,45.0,90%\n"
        "2026-08-18 12:00:01,72,46.0,90%\n",
        encoding="utf-8",
    )

    # 3. raw/acc.csv (with acceleration vectors)
    acc_csv = raw_dir / "acc.csv"
    acc_csv.write_text(
        "Timestamp_s,X_mG,Y_mG,Z_mG\n0.000,0,0,1000\n0.020,0,0,1000\n0.040,0,0,1000\n",
        encoding="utf-8",
    )

    return session_dir


class TestResearchLoaderAndAudit:
    def test_load_session_single_device(self, sample_session_dir: Path):
        session = load_session(sample_session_dir)
        assert session.session_id == "20260818_120000"
        assert session.is_dual is False
        assert len(session.summary) == 2
        assert "acc" in session.streams

        acc_df = session.get_stream("acc")
        assert acc_df is not None
        assert "ACC_Mag_mG" in acc_df.columns
        assert acc_df["ACC_Mag_mG"].iloc[0] == pytest.approx(1000.0)

    def test_verify_session_integrity(self, sample_session_dir: Path):
        report = verify_session_integrity(sample_session_dir)
        assert report["session_id"] == "20260818_120000"
        assert "acc" in report["streams"]

        acc_audit = report["streams"]["acc"]
        assert acc_audit["sample_count"] == 3
        assert acc_audit["average_hz"] == pytest.approx(75.0, rel=1e-1)
        assert acc_audit["gap_count"] == 0
