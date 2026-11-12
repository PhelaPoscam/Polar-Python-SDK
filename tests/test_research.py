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
        # 3 samples 20 ms apart: 50 Hz
        assert acc_audit["average_hz"] == pytest.approx(50.0, rel=1e-2)
        assert acc_audit["gap_count"] == 0

    def test_audit_merges_per_sample_rows_into_packets(self, tmp_path: Path):
        from polar_ble_sdk.research.audit import audit_csv_stream

        rows = ["Timestamp_s,X_mG,Y_mG,Z_mG"]
        for pkt in range(10):  # 10 packets of 4 samples, 80 ms apart = 50 Hz
            rows += [f"{pkt * 0.08:.3f},0,0,1000"] * 4
        csv_path = tmp_path / "acc.csv"
        csv_path.write_text("\n".join(rows), encoding="utf-8")

        audit = audit_csv_stream(csv_path)
        assert audit.packet_count == 10
        assert audit.gap_count == 0
        assert audit.average_hz == pytest.approx(50.0, rel=1e-2)

    def test_lazy_research_symbols_from_top_level(self):
        import polar_ble_sdk

        assert hasattr(polar_ble_sdk, "load_session")
        assert hasattr(polar_ble_sdk, "verify_session_integrity")
        assert hasattr(polar_ble_sdk, "PolarSessionData")
        assert polar_ble_sdk.load_session is load_session


def test_validation_plots_with_artifacts(tmp_path: Path):
    import pandas as pd

    from polar_ble_sdk.research.report import generate_validation_plots

    w = pd.DataFrame(
        {
            "start": pd.date_range("2026-01-01", periods=5, freq="60s"),
            "ref_hr": [60.0, 61, 62, 63, 64],
            "ppg_hr": [60.0, 61, 90, 63, 64],
            "ref_rmssd": [40.0, 42, 41, 39, 45],
            "ppg_rmssd": [41.0, 42, 80, 40, 44],
            "ref_ok": True,
            "artifact": [False, False, True, False, False],
        }
    )
    paths = generate_validation_plots(w, tmp_path)
    assert {p.name for p in paths} == {
        "bland_altman_hr.png",
        "bland_altman_rmssd.png",
        "time_series.png",
    }


def test_loader_maps_raw_streams_to_host_time(sample_session_dir: Path):
    meta_path = sample_session_dir / "session_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["clock_zero_points"] = {"acc_host_epoch_ns": 1_790_000_000 * 10**9}
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    acc = load_session(sample_session_dir).get_stream("acc")
    assert acc is not None
    gap = acc["Host_Time"].iloc[2] - acc["Host_Time"].iloc[0]
    assert gap.total_seconds() == pytest.approx(0.04)
