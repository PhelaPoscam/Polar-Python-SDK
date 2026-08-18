"""Unit tests for PMD MeasurementSettings serialization and deserialization."""

from polar_ble_sdk._pmd.constants import (
    PmdControlOperationCode,
    PmdControlPointErrorCode,
    PmdMeasurementType,
    PmdSettingType,
)
from polar_ble_sdk._pmd.models.measurement_settings import MeasurementSettings


class TestMeasurementSettings:
    def test_to_bytes_serialization(self):
        # Configure ECG settings: Sample Rate = 130 (2 bytes), Resolution = 14 (2 bytes)
        settings = MeasurementSettings(
            measurement_type=PmdMeasurementType.ECG,
            settings=[
                MeasurementSettings.SettingType(
                    type=PmdSettingType.SAMPLE_RATE, values=[130]
                ),
                MeasurementSettings.SettingType(
                    type=PmdSettingType.RESOLUTION, values=[14]
                ),
            ],
        )
        data = settings.to_bytes()

        # Expected:
        # Byte 0: START (0x02)
        # Byte 1: Type ECG (0x00)
        # Setting 0: Type SAMPLE_RATE (0x00), Length (0x01), Value (130 -> 0x82, 0x00)
        # Setting 1: Type RESOLUTION (0x01), Length (0x01), Value (14 -> 0x0E, 0x00)
        assert data[0] == PmdControlOperationCode.START
        assert data[1] == PmdMeasurementType.ECG.value
        assert data[2] == PmdSettingType.SAMPLE_RATE.value
        assert data[3] == 1  # 1 value
        assert int.from_bytes(data[4:6], "little") == 130
        assert data[6] == PmdSettingType.RESOLUTION.value
        assert data[7] == 1
        assert int.from_bytes(data[8:10], "little") == 14

    def test_from_bytes_response_parsing(self):
        # Simulated response from device:
        # Byte 0: 0xF0 (Control Point response)
        # Byte 1: 0x01 (Opcode GET)
        # Byte 2: 0x02 (Measurement Type ACC)
        # Byte 3: 0x00 (Error Code SUCCESS)
        # Byte 4: 0x00 (More frames = False)
        # Setting: SAMPLE_RATE (0x00), Array Length = 2, Values = 52, 208 (each 2 bytes)
        raw = bytearray(
            [
                0xF0,
                0x01,
                PmdMeasurementType.ACC.value,
                PmdControlPointErrorCode.SUCCESS.value,
                0x00,
                PmdSettingType.SAMPLE_RATE.value,
                0x02,  # 2 values
                *(52).to_bytes(2, "little"),
                *(208).to_bytes(2, "little"),
            ]
        )

        parsed = MeasurementSettings.from_bytes(raw)
        assert parsed.measurement_type == PmdMeasurementType.ACC
        assert parsed.error_code == PmdControlPointErrorCode.SUCCESS
        assert parsed.more_frames is False
        assert len(parsed.settings) == 1
        assert parsed.settings[0].type == PmdSettingType.SAMPLE_RATE
        assert parsed.settings[0].values == [52, 208]
