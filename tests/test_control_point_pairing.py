"""Regression tests for PMD control-point request/response pairing.

The device answers every control-point request, but a reply is only removed
from the queue when a caller reads it. Commands that ignore their reply (SDK
mode, stop) therefore leave one queued. Reading blindly then pairs each request
with the previous request's reply, which silently masked a rejected ACC start:
the Verity Sense needs CHANNELS=3, and a start sent without it is refused.
"""

from typing import Any
from unittest.mock import patch

import pytest

from polar_ble_sdk._pmd import PolarDevice
from polar_ble_sdk._pmd.constants import (
    PmdControlOperationCode,
    PmdControlPointErrorCode,
    PmdMeasurementType,
    PmdSettingType,
)
from polar_ble_sdk._pmd.exceptions import ControlPointResponseError

SDK_MODE_TYPE = 0x09
CONTROL_POINT_UUID = "FB005C82-02E7-F387-1CAD-8ACD2D8DF0C8"


def response(
    op: int,
    measurement_type: int,
    error: PmdControlPointErrorCode = PmdControlPointErrorCode.SUCCESS,
    settings: tuple[tuple[PmdSettingType, list[int]], ...] = (),
) -> bytearray:
    """Build a device control-point response: F0 <op> <type> <error> <more> ..."""
    data = bytearray([0xF0, op, measurement_type, error, 0x00])
    for setting_type, values in settings:
        data.append(setting_type.value)
        data.append(len(values))
        for value in values:
            data.extend(value.to_bytes(setting_type.field_size, "little"))
    return data


ACC_AVAILABLE_SETTINGS = (
    (PmdSettingType.SAMPLE_RATE, [52]),
    (PmdSettingType.RESOLUTION, [16]),
    (PmdSettingType.RANGE, [8]),
    (PmdSettingType.CHANNELS, [3]),
)


class FakeClient:
    """Stands in for BleakClient, scripting the device side of the exchange."""

    def __init__(self, device: PolarDevice) -> None:
        self._device = device
        self.writes: list[bytearray] = []
        self.reply: Any = None

    async def write_gatt_char(self, _uuid: Any, payload: bytearray, **_kw: Any) -> None:
        self.writes.append(bytearray(payload))
        if self.reply is not None:
            self._device._queue_pmd_control.put_nowait(self.reply(payload))


def make_device() -> tuple[PolarDevice, FakeClient]:
    device = PolarDevice("AA:BB:CC:DD:EE:FF")
    client = FakeClient(device)
    device._client = client  # type: ignore[assignment]
    return device, client


class TestControlPointPairing:
    @pytest.mark.asyncio
    async def test_stale_sdk_reply_does_not_break_settings_fetch(self) -> None:
        """The reply enable_sdk_mode leaves queued must not be read as the GET reply."""
        device, client = make_device()
        device._queue_pmd_control.put_nowait(
            response(PmdControlOperationCode.GET, SDK_MODE_TYPE)
        )
        client.reply = lambda _p: response(
            PmdControlOperationCode.GET,
            PmdMeasurementType.ACC,
            settings=ACC_AVAILABLE_SETTINGS,
        )

        settings = await device.request_stream_settings(PmdMeasurementType.ACC)

        by_type = {s.type: s.values for s in settings.settings}
        assert by_type[PmdSettingType.SAMPLE_RATE] == [52]
        assert by_type[PmdSettingType.CHANNELS] == [3]

    @pytest.mark.asyncio
    async def test_reply_for_other_measurement_type_is_skipped(self) -> None:
        device, client = make_device()
        device._queue_pmd_control.put_nowait(
            response(
                PmdControlOperationCode.GET,
                PmdMeasurementType.PPG,
                settings=((PmdSettingType.SAMPLE_RATE, [135]),),
            )
        )
        client.reply = lambda _p: response(
            PmdControlOperationCode.GET,
            PmdMeasurementType.ACC,
            settings=ACC_AVAILABLE_SETTINGS,
        )

        settings = await device.request_stream_settings(PmdMeasurementType.ACC)

        assert settings.measurement_type == PmdMeasurementType.ACC

    @pytest.mark.asyncio
    async def test_rejected_start_raises_despite_queued_success(self) -> None:
        """A stale SUCCESS must not be mistaken for the START reply.

        This is the bug that made a channel-less ACC start look successful while
        the device had actually refused it.
        """
        device, client = make_device()
        device._queue_pmd_control.put_nowait(
            response(PmdControlOperationCode.GET, PmdMeasurementType.ACC)
        )
        client.reply = lambda _p: response(
            PmdControlOperationCode.START,
            PmdMeasurementType.ACC,
            error=PmdControlPointErrorCode.ERROR_INVALID_NUMBER_OF_CHANNELS,
        )

        with pytest.raises(
            ControlPointResponseError, match="ERROR_INVALID_NUMBER_OF_CHANNELS"
        ):
            await device.start_acc_stream(lambda _d: None, 52, 16, 8)

    @pytest.mark.asyncio
    async def test_accepted_start_parses_factor(self) -> None:
        device, client = make_device()
        client.reply = lambda _p: response(
            PmdControlOperationCode.START,
            PmdMeasurementType.ACC,
            settings=((PmdSettingType.FACTOR, [0x3F800000]),),  # 1.0f
        )

        await device.start_acc_stream(lambda _d: None, 52, 16, 8, 3)

        assert device._factors[PmdMeasurementType.ACC] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_missing_reply_times_out_to_none(self) -> None:
        device, _client = make_device()

        result = await device._read_control_response(
            PmdControlOperationCode.GET, PmdMeasurementType.ACC, timeout=0.05
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_settings_request_raises_when_device_is_silent(self) -> None:
        device, _client = make_device()
        original = device._read_control_response

        async def quick(op, measurement_type=None, timeout=0.05):
            return await original(op, measurement_type, timeout=0.05)

        with (
            patch.object(device, "_read_control_response", quick),
            pytest.raises(ControlPointResponseError, match="No settings response"),
        ):
            await device.request_stream_settings(PmdMeasurementType.ACC)
