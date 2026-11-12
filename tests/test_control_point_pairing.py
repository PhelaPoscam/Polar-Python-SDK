"""Regression tests for PMD control-point request/response pairing.

The device answers every control-point request, but a reply is only removed
from the queue when a caller reads it. Commands that ignore their reply (stop)
or time out therefore leave one queued. Reading blindly then pairs each request
with the previous request's reply, which silently masked a rejected ACC start:
the Verity Sense needs CHANNELS=3, and a start sent without it is refused.
"""

import asyncio
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


class TestControlPointErrors:
    @pytest.mark.asyncio
    async def test_short_error_reply_raises_library_error(self) -> None:
        device, client = make_device()
        client.reply = lambda _p: bytearray(
            [0xF0, PmdControlOperationCode.START, PmdMeasurementType.ACC]
        )
        with pytest.raises(ControlPointResponseError):
            await device.start_acc_stream(lambda _d: None, 52, 16, 8)

    @pytest.mark.asyncio
    async def test_unknown_error_code_raises_library_error(self) -> None:
        device, client = make_device()
        client.reply = lambda _p: bytearray(
            [0xF0, PmdControlOperationCode.GET, PmdMeasurementType.ACC, 0xEE]
        )
        with pytest.raises(ControlPointResponseError):
            await device.request_stream_settings(PmdMeasurementType.ACC)

    @pytest.mark.asyncio
    async def test_rejected_settings_request_raises(self) -> None:
        device, client = make_device()
        client.reply = lambda _p: response(
            PmdControlOperationCode.GET,
            PmdMeasurementType.ACC,
            error=PmdControlPointErrorCode.ERROR_NOT_SUPPORTED,
        )
        with pytest.raises(ControlPointResponseError, match="ERROR_NOT_SUPPORTED"):
            await device.request_stream_settings(PmdMeasurementType.ACC)


class TestMultiPacketReplies:
    @pytest.mark.asyncio
    async def test_current_format_continuation_repeats_the_header(self) -> None:
        """Polar SDK master: each continuation is F0 op type status more + payload."""
        device, client = make_device()
        first = response(
            PmdControlOperationCode.GET,
            PmdMeasurementType.ACC,
            settings=((PmdSettingType.SAMPLE_RATE, [26, 52]),),
        )
        first[4] = 0x01
        second = response(
            PmdControlOperationCode.GET,
            PmdMeasurementType.ACC,
            settings=((PmdSettingType.RANGE, [2, 4, 8]),),
        )

        def reply(_payload: bytearray) -> bytearray:
            device._handle_pmd_control(0, first)
            return second

        client.reply = reply
        settings = await device.request_stream_settings(PmdMeasurementType.ACC)
        by_type = {s.type: s.values for s in settings.settings}
        assert by_type[PmdSettingType.SAMPLE_RATE] == [26, 52]
        assert by_type[PmdSettingType.RANGE] == [2, 4, 8]

    @pytest.mark.asyncio
    async def test_error_reply_has_no_more_flag(self) -> None:
        """Byte 4 of an error reply is not a "more" flag: report the error now."""
        device, client = make_device()
        rejected = response(
            PmdControlOperationCode.START,
            PmdMeasurementType.ACC,
            error=PmdControlPointErrorCode.ERROR_INVALID_SAMPLE_RATE,
        )
        rejected[4] = 0x01
        client.reply = lambda _p: rejected
        with pytest.raises(ControlPointResponseError, match="INVALID_SAMPLE_RATE"):
            await asyncio.wait_for(
                device.start_acc_stream(lambda _d: None, 1, 16, 8), 1
            )

    @pytest.mark.asyncio
    async def test_settings_spread_over_two_packets_are_merged(self) -> None:
        """Polar SDK 5.0.0 format: continuation = more flag + payload."""
        device, client = make_device()
        first = response(
            PmdControlOperationCode.GET,
            PmdMeasurementType.ACC,
            settings=((PmdSettingType.SAMPLE_RATE, [26, 52]),),
        )
        first[4] = 0x01  # more packets follow
        second = bytearray([0x00])  # last continuation
        for setting_type, values in ((PmdSettingType.RANGE, [2, 4, 8]),):
            second.append(setting_type.value)
            second.append(len(values))
            for value in values:
                second.extend(value.to_bytes(setting_type.field_size, "little"))

        def reply(_payload: bytearray) -> bytearray:
            device._queue_pmd_control.put_nowait(first)
            return second

        client.reply = reply
        settings = await device.request_stream_settings(PmdMeasurementType.ACC)
        by_type = {s.type: s.values for s in settings.settings}
        assert by_type[PmdSettingType.SAMPLE_RATE] == [26, 52]
        assert by_type[PmdSettingType.RANGE] == [2, 4, 8]

    @pytest.mark.asyncio
    async def test_missing_continuation_is_an_error_not_a_truncation(self) -> None:
        device, client = make_device()
        first = response(PmdControlOperationCode.GET, PmdMeasurementType.ACC)
        first[4] = 0x01
        client.reply = lambda _p: first
        with pytest.raises(ControlPointResponseError):
            await asyncio.wait_for(
                device.request_stream_settings(PmdMeasurementType.ACC), 10
            )

    def test_start_reply_stores_factor_before_start_stream_resumes(self) -> None:
        """A data frame dispatched right after the START reply must be scaled."""
        import struct

        device, _client = make_device()
        raw = struct.unpack("<I", struct.pack("<f", 0.244))[0]
        device._handle_pmd_control(
            0,
            response(
                PmdControlOperationCode.START,
                PmdMeasurementType.ACC,
                settings=((PmdSettingType.FACTOR, [raw]),),
            ),
        )
        assert device._factors[PmdMeasurementType.ACC] == pytest.approx(0.244)


class TestDeviceMessages:
    def test_device_initiated_stop_is_reported_not_queued(self) -> None:
        events: list[tuple[str, str]] = []
        device = PolarDevice(
            "AA:BB:CC:DD:EE:FF", pmd_event_callback=lambda m, s: events.append((m, s))
        )
        device._handle_pmd_control(0, bytearray([0x01, PmdMeasurementType.PPG]))
        assert device._queue_pmd_control.empty()
        assert events == [("Device stopped stream: PPG", "error")]

    def test_old_format_continuation_is_queued_while_more_is_pending(self) -> None:
        device = PolarDevice("AA:BB:CC:DD:EE:FF")
        first = response(PmdControlOperationCode.GET, PmdMeasurementType.ACC)
        first[4] = 0x01
        device._handle_pmd_control(0, first)
        device._handle_pmd_control(0, bytearray([0x00, 0x02, 0x01, 0x08, 0x00]))
        assert device._queue_pmd_control.qsize() == 2


class TestSdkMode:
    @pytest.mark.parametrize(
        "status",
        [
            PmdControlPointErrorCode.SUCCESS,
            PmdControlPointErrorCode.ERROR_ALREADY_IN_STATE,
        ],
    )
    @pytest.mark.asyncio
    async def test_enable_accepts_success_and_already_in_state(self, status) -> None:
        device, client = make_device()
        client.reply = lambda _p: response(
            PmdControlOperationCode.START, SDK_MODE_TYPE, error=status
        )
        await device.enable_sdk_mode()
        assert client.writes == [bytearray([PmdControlOperationCode.START, 0x09])]

    @pytest.mark.asyncio
    async def test_refused_enable_raises(self) -> None:
        """Watches and old firmware refuse SDK mode; it must not be logged as on."""
        device, client = make_device()
        client.reply = lambda _p: response(
            PmdControlOperationCode.START,
            SDK_MODE_TYPE,
            error=PmdControlPointErrorCode.ERROR_NOT_SUPPORTED,
        )
        with pytest.raises(ControlPointResponseError, match="ERROR_NOT_SUPPORTED"):
            await device.enable_sdk_mode()

    @pytest.mark.asyncio
    async def test_silent_device_raises(self) -> None:
        device, _client = make_device()
        with pytest.raises(ControlPointResponseError, match="No reply"):
            await device.enable_sdk_mode(timeout=0.05)


class TestStreamStartRetry:
    @pytest.mark.asyncio
    async def test_failed_start_is_retried_then_succeeds(self, monkeypatch) -> None:
        from polar_ble_sdk.connector.stream import base

        monkeypatch.setattr(base, "STREAM_RETRY_DELAY_S", 0)
        attempts: list[int] = []

        async def start() -> None:
            attempts.append(1)
            if len(attempts) < 2:
                raise ControlPointResponseError("No start response for ECG")

        dev = base.BasePolarDevice(None, verbose=False)
        assert await dev._start_with_retry("ECG", start)
        assert len(attempts) == 2
        assert dev.stream_errors == {}

    @pytest.mark.asyncio
    async def test_start_that_keeps_failing_is_recorded(self, monkeypatch) -> None:
        from polar_ble_sdk.connector.stream import base

        monkeypatch.setattr(base, "STREAM_RETRY_DELAY_S", 0)
        events: list[tuple[str, str]] = []

        async def start() -> None:
            raise ControlPointResponseError("Device rejected stream")

        dev = base.BasePolarDevice(
            None, verbose=False, log_callback=lambda m, s: events.append((m, s))
        )
        assert not await dev._start_with_retry("ECG", start)
        assert "Device rejected stream" in dev.stream_errors["ECG"]
        assert events[-1][1] == "error"

    @pytest.mark.asyncio
    async def test_retry_after_lost_reply_counts_as_started(self) -> None:
        """A retry answered "already in state" means the stream is running."""
        device, client = make_device()
        client.reply = lambda _p: response(
            PmdControlOperationCode.START,
            PmdMeasurementType.ECG,
            error=PmdControlPointErrorCode.ERROR_ALREADY_IN_STATE,
        )
        await device.start_ecg_stream(lambda _d: None, 130, 14)

    @pytest.mark.asyncio
    async def test_unadvertised_stream_is_recorded(self) -> None:
        from polar_ble_sdk.connector.stream.base import BasePolarDevice

        dev = BasePolarDevice(None, verbose=False)
        ok = await dev._start_pmd_stream(
            lambda _d: None,
            PmdMeasurementType.PPG,
            "start_ppg_stream",
            lambda _d: None,
            [],  # e.g. the feature read failed
            {"sample_rate": 135},
            "PPG",
        )
        assert not ok
        assert dev.stream_errors == {"PPG": "not advertised by device"}
