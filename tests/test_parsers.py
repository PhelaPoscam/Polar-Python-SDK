"""Unit tests for binary protocol frame parsing and delta decompression."""

import pytest

from polar_ble_sdk._pmd.constants import TIMESTAMP_OFFSET
from polar_ble_sdk._pmd.models import (
    ACCData,
    ECGData,
    PPGData,
    PPIData,
)
from polar_ble_sdk._pmd.parsers.compression import (
    parse_delta_frame_ref_samples,
    parse_delta_frames_all,
)
from polar_ble_sdk._pmd.parsers.hr import parse_hr_data
from polar_ble_sdk._pmd.parsers.polar import parse_polar_data


class TestHeartRateParser:
    def test_hr_8bit_no_rr(self):
        # flags=0x00 (8-bit HR, no RR), hr=72
        raw = bytearray([0x00, 72])
        data = parse_hr_data(raw)
        assert data.heartrate == 72
        assert data.rr_intervals == []

    def test_hr_16bit_no_rr(self):
        # flags=0x01 (16-bit HR, no RR), hr=280
        raw = bytearray([0x01, 0x18, 0x01])  # 0x0118 = 280
        data = parse_hr_data(raw)
        assert data.heartrate == 280
        assert data.rr_intervals == []

    def test_hr_8bit_with_rr(self):
        # flags=0x10 (8-bit HR, RR present), hr=60, RR=1024 raw (1000.0 ms)
        raw = bytearray([0x10, 60, 0x00, 0x04])  # 0x0400 = 1024
        data = parse_hr_data(raw)
        assert data.heartrate == 60
        assert len(data.rr_intervals) == 1
        assert data.rr_intervals[0] == pytest.approx(1000.0, rel=1e-3)

    def test_hr_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            parse_hr_data(bytearray([0x00]))


class TestDeltaCompressionEngine:
    def test_empty_delta_frames(self):
        assert (
            parse_delta_frames_all(
                [], channels=3, resolution=16, data_type="signed_int"
            )
            == []
        )

    def test_ref_samples_signed(self):
        # 3 channels, 16-bit (2 bytes each) -> 6 bytes
        # ch0 = 100, ch1 = -50 (0xFFCE), ch2 = 1000
        raw = bytearray()
        raw.extend((100).to_bytes(2, "little", signed=True))
        raw.extend((-50).to_bytes(2, "little", signed=True))
        raw.extend((1000).to_bytes(2, "little", signed=True))

        refs = parse_delta_frame_ref_samples(
            raw, channels=3, resolution=16, data_type="signed_int"
        )
        assert refs == [100, -50, 1000]

    def test_delta_frame_decompression_roundtrip(self):
        # 1 channel, 8-bit resolution.
        # Ref sample = 10.
        # Delta 1 = +2 (sample=12), Delta 2 = -3 (sample=9)
        # Delta header: delta_size=4 bits, sample_count=2
        # Bits needed: 2 * 4 * 1 = 8 bits = 1 byte
        # Delta 1: 0010 (+2), Delta 2: 1101 (-3) -> packed: 0b11010010 = 0xD2
        raw = bytearray([10, 4, 2, 0xD2])
        samples = parse_delta_frames_all(
            raw, channels=1, resolution=8, data_type="signed_int"
        )
        assert len(samples) == 3
        assert samples[0] == [10]
        assert samples[1] == [12]
        assert samples[2] == [9]


class TestPmdDataFrameParsers:
    def test_ecg_raw_parsing(self):
        # Header: Type=0 (ECG), Timestamp=1000ns, FrameType=0 (raw Type 0)
        # Content: 2 samples, 3 bytes each = 6 bytes
        # sample1 = 1234 uV, sample2 = -567 uV
        header = bytearray([0])  # ECG
        header.extend((1000).to_bytes(8, "little"))  # ts
        header.append(0x00)  # raw type 0
        content = bytearray()
        content.extend((1234).to_bytes(3, "little", signed=True))
        content.extend((-567).to_bytes(3, "little", signed=True))
        raw = header + content

        parsed = parse_polar_data(raw, lambda _: 1.0)
        assert isinstance(parsed, ECGData)
        assert parsed.timestamp == 1000 + TIMESTAMP_OFFSET
        assert parsed.data == [1234, -567]

    def test_acc_raw_type_0(self):
        # Type=2 (ACC), raw Type 0 (1 byte per axis)
        header = bytearray([2])
        header.extend((500).to_bytes(8, "little"))
        header.append(0x00)  # raw type 0
        # 1 sample: x=10, y=-20, z=30
        content = bytearray()
        content.extend((10).to_bytes(1, "little", signed=True))
        content.extend((-20).to_bytes(1, "little", signed=True))
        content.extend((30).to_bytes(1, "little", signed=True))

        parsed = parse_polar_data(header + content, lambda _: 1.0)
        assert isinstance(parsed, ACCData)
        assert parsed.data == [(10, -20, 30)]

    def test_acc_raw_type_1(self):
        # Type=2 (ACC), raw Type 1 (2 bytes per axis)
        header = bytearray([2])
        header.extend((500).to_bytes(8, "little"))
        header.append(0x01)  # raw type 1
        # 1 sample: x=1000, y=-500, z=2000
        content = bytearray()
        content.extend((1000).to_bytes(2, "little", signed=True))
        content.extend((-500).to_bytes(2, "little", signed=True))
        content.extend((2000).to_bytes(2, "little", signed=True))

        parsed = parse_polar_data(header + content, lambda _: 1.0)
        assert isinstance(parsed, ACCData)
        assert parsed.data == [(1000, -500, 2000)]

    def test_ppg_raw_type_0(self):
        # Type=1 (PPG), raw Type 0 (4 channels x 3 bytes = 12 bytes per sample)
        header = bytearray([1])
        header.extend((100).to_bytes(8, "little"))
        header.append(0x00)
        content = bytearray()
        # 1 sample: ch0=1000, ch1=2000, ch2=3000, ambient=400
        content.extend((1000).to_bytes(3, "little", signed=True))
        content.extend((2000).to_bytes(3, "little", signed=True))
        content.extend((3000).to_bytes(3, "little", signed=True))
        content.extend((400).to_bytes(3, "little", signed=True))

        parsed = parse_polar_data(header + content, lambda _: 1.0)
        assert isinstance(parsed, PPGData)
        assert parsed.samples == [[1000, 2000, 3000, 400]]

    def test_ppi_raw_type_0(self):
        # Type=3 (PPI), raw Type 0 (6-byte chunk: HR, PPI uint16, ErrEst uint16, Status)
        header = bytearray([3])
        header.extend((1000_000_000).to_bytes(8, "little"))
        header.append(0x00)
        # sample: HR=60, PPI=850ms, ErrEst=15ms, Status=0x06 (contact detected + supported)
        content = bytearray(
            [
                60,
                *(850).to_bytes(2, "little"),
                *(15).to_bytes(2, "little"),
                0x06,
            ]
        )

        parsed = parse_polar_data(header + content, lambda _: 1.0)
        assert isinstance(parsed, PPIData)
        assert len(parsed.samples) == 1
        s = parsed.samples[0]
        assert s.hr == 60
        assert s.ppi == 850
        assert s.error_estimate == 15
        assert s.skin_contact_status is True
        assert s.skin_contact_supported is True
        assert s.invalid_ppi is False
