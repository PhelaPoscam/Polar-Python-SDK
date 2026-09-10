"""Unit tests for PolarAdapter with link watchdog and auto-reconnect fallback."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from polar_ble_sdk.connector.adapter import PolarAdapter
from polar_ble_sdk.connector.stream.base import (
    DISCONNECT_INFO,
    DisconnectReason,
    looks_like_bond_break,
)


class TestPolarAdapter:
    def test_adapter_initialization(self) -> None:
        received_statuses: list[tuple[str, str]] = []

        def on_status(dev: str, msg: str) -> None:
            received_statuses.append((dev, msg))

        h10_hr_called = False

        def on_h10_hr(data: object) -> None:
            nonlocal h10_hr_called
            h10_hr_called = True

        adapter = PolarAdapter(
            h10_target="H10_TEST",
            sense_target="SENSE_TEST",
            enable_sense_gyro=True,
            enable_sense_mag=False,
            h10_callbacks={"hr": on_h10_hr},
            sense_callbacks={"ppg": None},
            status_callback=on_status,
            enable_watchdog=True,
            watchdog_interval=2.0,
            freeze_timeout=5.0,
            reconnect_cooldown=0.5,
        )

        assert adapter.h10_target == "H10_TEST"
        assert adapter.sense_target == "SENSE_TEST"
        assert adapter.enable_sense_gyro is True
        assert adapter.enable_sense_mag is False
        assert adapter.enable_watchdog is True
        assert adapter.watchdog_interval == 2.0
        assert adapter.freeze_timeout == 5.0
        assert adapter.reconnect_cooldown == 0.5
        assert adapter.is_h10_connected is False
        assert adapter.is_sense_connected is False
        assert adapter.proxy_h10.polar_device is None
        assert adapter.proxy_sense.polar_device is None
        assert adapter.proxy_h10.stream_errors == {}

    def test_callback_wrapping_and_packet_timestamps(self) -> None:
        h10_received: list[object] = []
        sense_received: list[object] = []

        adapter = PolarAdapter(
            h10_callbacks={"ecg": lambda d: h10_received.append(d)},
            sense_callbacks={"ppg": lambda d: sense_received.append(d)},
        )

        assert adapter.last_h10_packet_time == 0.0
        assert adapter.last_sense_packet_time == 0.0

        t_before = time.monotonic()
        adapter.h10_callbacks["ecg"]((12345, [100, 200]))
        t_after = time.monotonic()

        assert len(h10_received) == 1
        assert t_before <= adapter.last_h10_packet_time <= t_after

        t_sense_before = time.monotonic()
        adapter.sense_callbacks["ppg"]((67890, [300, 400]))
        t_sense_after = time.monotonic()

        assert len(sense_received) == 1
        assert t_sense_before <= adapter.last_sense_packet_time <= t_sense_after

    def test_connector_proxies(self) -> None:
        adapter = PolarAdapter()

        # Before connection, attributes default safely
        assert adapter.proxy_h10.polar_device is None
        assert adapter.proxy_h10.stream_errors == {}
        assert adapter.proxy_sense.polar_device is None

        # Simulate active mock connection
        mock_h10 = MagicMock()
        mock_h10.polar_device._client.is_connected = True
        mock_h10.stream_errors = {"ECG": "failed"}
        adapter.conn_h10 = mock_h10

        assert adapter.proxy_h10.polar_device is mock_h10.polar_device
        assert adapter.proxy_h10.stream_errors == {"ECG": "failed"}
        assert adapter.is_h10_connected is True

    @pytest.mark.asyncio
    async def test_watchdog_detects_freeze(self) -> None:
        reconnect_triggered = asyncio.Event()

        adapter = PolarAdapter(
            enable_watchdog=True,
            watchdog_interval=0.05,
            freeze_timeout=0.1,
        )

        # Mock connected device
        mock_h10 = MagicMock()
        mock_h10.polar_device._client.is_connected = True
        adapter.conn_h10 = mock_h10
        adapter._running = True
        adapter._enable_h10_flag = True

        # Simulate packet received in the past (> freeze_timeout)
        adapter._last_h10_packet_time = time.monotonic() - 1.0

        async def fake_reconnect(*_args) -> None:
            reconnect_triggered.set()

        adapter._reconnect_h10 = fake_reconnect  # type: ignore[assignment]

        task = asyncio.create_task(adapter._watchdog_loop())
        try:
            await asyncio.wait_for(reconnect_triggered.wait(), timeout=1.0)
            assert reconnect_triggered.is_set()
        finally:
            adapter._running = False
            task.cancel()
            with contextlib_suppress():
                await task

    @pytest.mark.asyncio
    async def test_watchdog_detects_disconnect(self) -> None:
        reconnect_triggered = asyncio.Event()

        adapter = PolarAdapter(
            enable_watchdog=True,
            watchdog_interval=0.05,
            freeze_timeout=5.0,
        )

        # Mock client whose connection dropped
        mock_sense = MagicMock()
        mock_sense.polar_device._client.is_connected = False
        adapter.conn_sense = mock_sense
        adapter._running = True
        adapter._enable_sense_flag = True

        async def fake_reconnect(*_args) -> None:
            reconnect_triggered.set()

        adapter._reconnect_sense = fake_reconnect  # type: ignore[assignment]

        task = asyncio.create_task(adapter._watchdog_loop())
        try:
            await asyncio.wait_for(reconnect_triggered.wait(), timeout=1.0)
            assert reconnect_triggered.is_set()
        finally:
            adapter._running = False
            task.cancel()
            with contextlib_suppress():
                await task

    @pytest.mark.asyncio
    async def test_reconnect_h10_lifecycle(self) -> None:
        statuses: list[tuple[str, str]] = []

        def on_status(dev: str, msg: str) -> None:
            statuses.append((dev, msg))

        adapter = PolarAdapter(
            status_callback=on_status,
            reconnect_cooldown=0.01,
        )
        adapter._running = True
        adapter.h10_dev = MagicMock()

        mock_conn = MagicMock()
        mock_conn.stop_notify = AsyncMock()
        mock_conn.start_notify = AsyncMock()
        adapter.conn_h10 = mock_conn

        with patch.object(adapter, "_init_h10") as mock_init:

            def perform_init():
                adapter.conn_h10 = mock_conn

            mock_init.side_effect = perform_init

            await adapter._reconnect_h10()

        # Verified lifecycle: stopped old, re-initialized, started new, status notifications sent
        mock_conn.stop_notify.assert_awaited_once()
        mock_conn.start_notify.assert_awaited_once()
        assert adapter._reconnecting_h10 is False
        assert ("H10", "Watchdog: link lost; reconnecting...") in statuses
        assert ("H10", "Connected! Streaming...") in statuses
        assert adapter.last_h10_packet_time > 0

    @pytest.mark.asyncio
    async def test_clean_disconnect(self) -> None:
        adapter = PolarAdapter(
            watchdog_interval=0.05,
        )
        adapter._running = True

        # Attach mock devices
        mock_h10 = MagicMock()
        mock_h10.stop_notify = AsyncMock()
        mock_sense = MagicMock()
        mock_sense.stop_notify = AsyncMock()
        adapter.conn_h10 = mock_h10
        adapter.conn_sense = mock_sense

        # Start watchdog task
        adapter._watchdog_task = asyncio.create_task(adapter._watchdog_loop())

        await adapter.disconnect()

        assert adapter._running is False
        assert adapter._watchdog_task is None
        assert adapter.conn_h10 is None
        assert adapter.conn_sense is None
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
        adapter.h10_dev = MagicMock()

        mock_conn = MagicMock()
        mock_conn.stop_notify = AsyncMock()
        mock_conn.start_notify = AsyncMock(
            side_effect=Exception("Authentication Required (5)")
        )
        adapter.conn_h10 = mock_conn
        with patch.object(
            adapter, "_init_h10", lambda: setattr(adapter, "conn_h10", mock_conn)
        ):
            await adapter._reconnect_h10(DisconnectReason.LINK_LOSS)

        guidance = DISCONNECT_INFO[DisconnectReason.BOND_BROKEN][1]
        assert any(dev == "H10" and guidance in msg for dev, msg in statuses)


def contextlib_suppress():
    import contextlib

    return contextlib.suppress(asyncio.CancelledError)
