"""Unit tests for PolarAdapter with link watchdog and auto-reconnect fallback."""

from __future__ import annotations

import asyncio
import contextlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from polar_ble_sdk.connector.adapter import PolarAdapter
from polar_ble_sdk.connector.stream.base import (
    DISCONNECT_INFO,
    DisconnectReason,
    looks_like_bond_break,
)


def _stoppable_conn() -> MagicMock:
    """A connected connector whose stop_notify really disconnects its client."""
    conn = _connected_conn()

    async def stop() -> None:
        conn.polar_device._client.is_connected = False

    conn.stop_notify = AsyncMock(side_effect=stop)
    return conn


def _connected_conn() -> MagicMock:
    conn = MagicMock()
    conn.polar_device._client.is_connected = True
    return conn


class TestPolarAdapter:
    def test_adapter_initialization(self) -> None:
        adapter = PolarAdapter(
            h10_target="H10_TEST",
            sense_target="SENSE_TEST",
            enable_sense_gyro=True,
            enable_sense_mag=False,
            h10_callbacks={"hr": lambda _d: None},
            sense_callbacks={"ppg": None},
            status_callback=lambda _dev, _msg: None,
            enable_watchdog=True,
            watchdog_interval=2.0,
            freeze_timeout=5.0,
            reconnect_cooldown=0.5,
        )

        assert adapter.h10_target == "H10_TEST"
        assert adapter.sense_target == "SENSE_TEST"
        assert adapter.enable_sense_gyro is True
        assert adapter.enable_sense_mag is False
        assert adapter.watchdog_interval == 2.0
        assert adapter.freeze_timeout == 5.0
        assert adapter.reconnect_cooldown == 0.5
        assert adapter.h10.is_connected is False
        assert adapter.sense.is_connected is False
        assert adapter.h10.polar_device is None
        assert adapter.sense.polar_device is None
        assert adapter.h10.stream_errors == {}
        # None callbacks are dropped, so the connector is not asked for the stream
        assert "ppg" not in adapter.sense.callbacks

    def test_disabled_imu_callbacks_are_dropped(self) -> None:
        adapter = PolarAdapter(
            sense_callbacks={
                "ppg": lambda _d: None,
                "gyro": lambda _d: None,
                "mag": lambda _d: None,
            },
            enable_sense_gyro=False,
            enable_sense_mag=False,
        )
        assert set(adapter.sense.callbacks) == {"ppg"}

    def test_callback_wrapping_and_packet_timestamps(self) -> None:
        h10_received: list[object] = []
        sense_received: list[object] = []

        adapter = PolarAdapter(
            h10_callbacks={"ecg": h10_received.append},
            sense_callbacks={"ppg": sense_received.append},
        )

        assert adapter.h10.last_packet_time == 0.0
        assert adapter.sense.last_packet_time == 0.0

        t_before = time.monotonic()
        adapter.h10.callbacks["ecg"]((12345, [100, 200]))
        t_after = time.monotonic()

        assert len(h10_received) == 1
        assert t_before <= adapter.h10.last_packet_time <= t_after

        t_sense_before = time.monotonic()
        adapter.sense.callbacks["ppg"]((67890, [300, 400]))
        t_sense_after = time.monotonic()

        assert len(sense_received) == 1
        assert t_sense_before <= adapter.sense.last_packet_time <= t_sense_after

    def test_link_follows_the_live_connector(self) -> None:
        adapter = PolarAdapter()

        assert adapter.h10.polar_device is None
        assert adapter.h10.stream_errors == {}

        mock_h10 = _connected_conn()
        mock_h10.stream_errors = {"ECG": "failed"}
        adapter.h10.conn = mock_h10

        assert adapter.h10.polar_device is mock_h10.polar_device
        assert adapter.h10.stream_errors == {"ECG": "failed"}
        assert adapter.h10.is_connected is True

    @pytest.mark.asyncio
    async def test_watchdog_detects_freeze(self) -> None:
        reconnect_triggered = asyncio.Event()

        adapter = PolarAdapter(
            enable_watchdog=True,
            watchdog_interval=0.05,
            freeze_timeout=0.1,
        )
        adapter.h10.conn = _connected_conn()
        adapter.h10.enabled = True
        adapter._running = True
        # Last packet is older than freeze_timeout
        adapter.h10.last_packet_time = time.monotonic() - 1.0

        async def fake_reconnect(link, reason) -> None:
            assert link is adapter.h10
            assert reason is DisconnectReason.STREAM_FROZEN
            reconnect_triggered.set()

        adapter._reconnect = fake_reconnect  # type: ignore[assignment]

        task = asyncio.create_task(adapter._watchdog_loop())
        try:
            await asyncio.wait_for(reconnect_triggered.wait(), timeout=1.0)
        finally:
            adapter._running = False
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    @pytest.mark.asyncio
    async def test_watchdog_detects_disconnect(self) -> None:
        reconnect_triggered = asyncio.Event()

        adapter = PolarAdapter(
            enable_watchdog=True,
            watchdog_interval=0.05,
            freeze_timeout=5.0,
        )
        mock_sense = MagicMock()
        mock_sense.polar_device._client.is_connected = False
        adapter.sense.conn = mock_sense
        adapter.sense.enabled = True
        adapter._running = True

        async def fake_reconnect(link, reason) -> None:
            assert link is adapter.sense
            assert reason is DisconnectReason.LINK_LOSS
            reconnect_triggered.set()

        adapter._reconnect = fake_reconnect  # type: ignore[assignment]

        task = asyncio.create_task(adapter._watchdog_loop())
        try:
            await asyncio.wait_for(reconnect_triggered.wait(), timeout=1.0)
        finally:
            adapter._running = False
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    @pytest.mark.asyncio
    async def test_reconnect_lifecycle(self) -> None:
        statuses: list[tuple[str, str]] = []

        adapter = PolarAdapter(
            status_callback=lambda dev, msg: statuses.append((dev, msg)),
            reconnect_cooldown=0.01,
        )
        adapter._running = True
        adapter.h10.dev = MagicMock()

        mock_conn = _stoppable_conn()
        mock_conn.start_notify = AsyncMock()
        adapter.h10.conn = mock_conn

        with patch.object(
            adapter.h10, "build", lambda: setattr(adapter.h10, "conn", mock_conn)
        ):
            await adapter._reconnect(adapter.h10)

        # Stopped the old link, rebuilt it, started it, reported both transitions
        mock_conn.stop_notify.assert_awaited_once()
        mock_conn.start_notify.assert_awaited_once()
        assert adapter.h10.reconnecting is False
        assert ("H10", "Watchdog: link lost; reconnecting...") in statuses
        assert ("H10", "Connected! Streaming...") in statuses
        assert adapter.h10.last_packet_time > 0

    @pytest.mark.asyncio
    async def test_clean_disconnect(self) -> None:
        adapter = PolarAdapter(watchdog_interval=0.05)
        adapter._running = True

        mock_h10 = MagicMock()
        mock_h10.stop_notify = AsyncMock()
        mock_sense = MagicMock()
        mock_sense.stop_notify = AsyncMock()
        adapter.h10.conn = mock_h10
        adapter.sense.conn = mock_sense

        adapter._watchdog_task = asyncio.create_task(adapter._watchdog_loop())

        await adapter.disconnect()

        assert adapter._running is False
        assert adapter._watchdog_task is None
        assert adapter.h10.conn is None
        assert adapter.sense.conn is None
        mock_h10.stop_notify.assert_awaited_once()
        mock_sense.stop_notify.assert_awaited_once()


class TestDisconnectReason:
    def test_bond_break_signature(self) -> None:
        assert looks_like_bond_break(
            "Error (5): Access is denied. Authentication Required"
        )
        assert looks_like_bond_break("-2147023673 Insufficient encryption")
        assert not looks_like_bond_break("Connection timed out")

    @pytest.mark.asyncio
    async def test_reconnect_reports_bond_broken(self) -> None:
        statuses: list[tuple[str, str]] = []
        adapter = PolarAdapter(status_callback=lambda d, m: statuses.append((d, m)))
        adapter._running = True
        adapter.h10.dev = MagicMock()

        mock_conn = _stoppable_conn()
        mock_conn.start_notify = AsyncMock(
            side_effect=Exception("Authentication Required (5)")
        )
        adapter.h10.conn = mock_conn

        with patch.object(
            adapter.h10, "build", lambda: setattr(adapter.h10, "conn", mock_conn)
        ):
            await adapter._reconnect(adapter.h10, DisconnectReason.LINK_LOSS)

        guidance = DISCONNECT_INFO[DisconnectReason.BOND_BROKEN][1]
        assert any(dev == "H10" and guidance in msg for dev, msg in statuses)


class TestStreamSettingOverrides:
    @pytest.mark.asyncio
    async def test_unsupported_override_falls_back_to_device_value(self) -> None:
        from types import SimpleNamespace

        from polar_ble_sdk._pmd.constants import PmdMeasurementType, PmdSettingType
        from polar_ble_sdk.connector.stream.base import BasePolarDevice

        calls: list[dict] = []

        class FakePmd:
            async def request_stream_settings(self, _mt):
                return SimpleNamespace(
                    settings=[
                        SimpleNamespace(type=PmdSettingType.SAMPLE_RATE, values=[52])
                    ]
                )

            async def start_acc_stream(self, _handler, **kwargs):
                calls.append(kwargs)

        warnings: list[str] = []
        dev = BasePolarDevice(
            None,
            verbose=False,
            acc_sample_rate=200,  # H10-only rate sent to a Sense in dual mode
            log_callback=lambda m, s: warnings.append(m) if s == "warning" else None,
        )
        dev.polar_device = FakePmd()
        ok = await dev._start_pmd_stream(
            lambda _d: None,
            PmdMeasurementType.ACC,
            "start_acc_stream",
            lambda _d: None,
            [PmdMeasurementType.ACC],
            {"sample_rate": 52},
            "ACC",
        )
        assert ok
        assert calls == [{"sample_rate": 52}]
        assert any("unsupported" in w for w in warnings)


class TestWatchdogHealth:
    def test_one_frozen_stream_is_detected_while_others_flow(self) -> None:
        adapter = PolarAdapter(
            sense_callbacks={"ppg": lambda _d: None, "acc": lambda _d: None}
        )
        link = adapter.sense
        link.conn = _connected_conn()
        link.mark_started()
        link.callbacks["ppg"](None)
        link.callbacks["acc"](None)
        now = time.monotonic()
        link.last_packet["ppg"] = now - 20.0  # PPG froze, ACC still arriving
        assert (
            link.stall_reason(now, freeze_timeout=8.0) is DisconnectReason.STREAM_FROZEN
        )
        assert link.frozen_streams == ["ppg"]

    def test_slow_streams_get_a_longer_budget(self) -> None:
        adapter = PolarAdapter(sense_callbacks={"ppi": lambda _d: None})
        link = adapter.sense
        link.conn = _connected_conn()
        link.mark_started()
        link.callbacks["ppi"](None)
        now = time.monotonic()
        link.last_packet["ppi"] = now - 12.0
        link.last_packet_time = now
        assert link.stall_reason(now, freeze_timeout=8.0) is None

    @pytest.mark.asyncio
    async def test_no_second_connection_while_old_client_is_stuck(self) -> None:
        statuses: list[str] = []
        adapter = PolarAdapter(
            status_callback=lambda _d, m: statuses.append(m), reconnect_cooldown=0
        )
        adapter._running = True
        adapter.h10.dev = MagicMock()
        stuck = _connected_conn()
        stuck.stop_notify = AsyncMock(side_effect=asyncio.TimeoutError)
        stuck.polar_device._client.disconnect = AsyncMock()  # never flips the flag
        adapter.h10.conn = stuck
        built: list[bool] = []
        with patch.object(adapter.h10, "build", lambda: built.append(True)):
            await adapter._reconnect(adapter.h10)
        assert not built
        assert any("still open" in m for m in statuses)
        assert adapter.h10.reconnecting is False

    @pytest.mark.asyncio
    async def test_add_link_manages_a_single_device(self) -> None:
        conn = _connected_conn()
        conn.start_notify = AsyncMock()
        factory = MagicMock(return_value=conn)
        adapter = PolarAdapter(enable_watchdog=False)
        link = adapter.add_link(
            "device",
            "Sense",
            MagicMock(address="AA"),
            factory,
            {"ppg": lambda _d: None},
        )
        assert await adapter.start() == {"h10": False, "sense": False, "device": True}
        assert link.conn is conn
        assert "ppg_callback" in factory.call_args.kwargs
        await adapter.disconnect()
