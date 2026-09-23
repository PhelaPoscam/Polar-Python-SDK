"""Tests for research loader unrolling wide ECG and PPG frame CSVs."""

import numpy as np
import pytest

from polar_ble_sdk.research.loader import (
    _parse_wide_ecg_csv,
    _parse_wide_ppg_csv,
    load_raw_stream,
)


class TestWideFrameLoaderRoundtrip:
    def test_ecg_wide_csv_unrolls_correctly(self, tmp_path):
        # Create a synthetic wide ECG CSV with 3 frames of 10 samples each
        # Nominal ECG rate is 130 Hz (dt ~ 0.007692 s)
        csv_file = tmp_path / "ecg.csv"
        rows = [
            "Timestamp_s,uV_Samples",
            "100.0,10,20,30,40,50,60,70,80,90,100",
            "100.076923,110,120,130,140,150,160,170,180,190,200",
            "100.153846,210,220,230,240,250,260,270,280,290,300",
        ]
        csv_file.write_text("\n".join(rows), encoding="utf-8")

        df = _parse_wide_ecg_csv(csv_file)
        assert not df.empty
        assert list(df.columns) == ["Timestamp_s", "uV", "ECG_uV"]
        assert len(df) == 30  # 3 frames * 10 samples
        assert df["uV"].iloc[0] == 10.0
        assert df["uV"].iloc[-1] == 300.0
        assert df["ECG_uV"].iloc[5] == 60.0

        # Verify monotonicity and spacing
        dt_diffs = np.diff(df["Timestamp_s"].values)
        assert np.all(dt_diffs > 0)
        assert np.allclose(dt_diffs, 1.0 / 130.0, atol=1e-3)
        # The frame timestamp belongs to the frame's last sample.
        assert df["Timestamp_s"].iloc[9] == 100.0
        assert df["Timestamp_s"].iloc[-1] == 100.153846

    def test_ppg_wide_csv_unrolls_correctly(self, tmp_path):
        # Create a synthetic wide PPG CSV with 2 frames of 2 samples (4 channels each)
        csv_file = tmp_path / "ppg.csv"
        rows = [
            "Timestamp_s,PPG_Samples",
            '50.0,"[100, 200, 300, 40]","[101, 201, 301, 41]"',
            '50.014815,"[102, 202, 302, 42]","[103, 203, 303, 43]"',
        ]
        csv_file.write_text("\n".join(rows), encoding="utf-8")

        df = _parse_wide_ppg_csv(csv_file)
        assert not df.empty
        assert list(df.columns) == ["Timestamp_s", "ch1", "ch2", "ch3", "ch4"]
        assert len(df) == 4  # 2 frames * 2 quad-samples = 4 samples
        assert df["ch1"].iloc[0] == 100.0
        assert df["ch4"].iloc[-1] == 43.0

    def test_load_raw_stream_routes_ecg_and_ppg(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        ecg_file = raw_dir / "ecg.csv"
        ecg_file.write_text(
            "Timestamp_s,uV_Samples\n1.0,10,20\n1.01538,30,40\n", encoding="utf-8"
        )

        df = load_raw_stream(raw_dir, "ecg")
        assert len(df) == 4
        assert "ECG_uV" in df.columns


def test_variable_size_ppg_frames_keep_true_sample_rate(tmp_path):
    """Delta-compressed PPG frames vary in size; spacing must follow each frame."""
    from polar_ble_sdk.research.loader import _parse_wide_ppg_csv
    from polar_ble_sdk.research.ppg import estimate_fs, split_segments

    fs, sizes = 135.0, [31, 52, 42, 48, 36, 45]
    lines, n_total = ["Timestamp_s,PPG_Samples"], 0
    for n in sizes:
        n_total += n
        ts = (n_total - 1) / fs  # timestamp of the frame's last sample
        lines.append(f"{ts:.6f}," + ",".join(['"[1, 2, 3, 4]"'] * n))
    csv_file = tmp_path / "ppg.csv"
    csv_file.write_text("\n".join(lines), encoding="utf-8")

    t = _parse_wide_ppg_csv(csv_file)["Timestamp_s"].to_numpy()
    assert estimate_fs(t) == pytest.approx(fs, rel=1e-3)
    assert len(split_segments(t, estimate_fs(t))) == 1
    assert t[0] == pytest.approx(0.0, abs=1e-6)
