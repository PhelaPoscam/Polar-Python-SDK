"""Polar BLE device adapter for Polar H10 and Verity Sense with auto-reconnect watchdog."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import Any

from .ble_discovery import discover_dual_polar_devices
from .stream import PolarH10, PolarVeritySense
from .stream.base import DISCONNECT_INFO, DisconnectReason, looks_like_bond_break

logger = logging.getLogger("polar_adapter")


class _ConnectorProxy:
    """Dynamic proxy that delegates attribute access (e.g. polar_device) to the active connector."""

    def __init__(self, adapter: PolarAdapter, target: str) -> None:
        self._adapter = adapter
        self._target = target

    @property
    def _conn(self) -> Any:
        return (
            self._adapter.conn_h10
            if self._target == "h10"
            else self._adapter.conn_sense
        )

    @property
    def polar_device(self) -> Any:
        return getattr(self._conn, "polar_device", None)

    @property
    def stream_errors(self) -> dict[str, str]:
        return getattr(self._conn, "stream_errors", {})

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


class PolarAdapter:
    """Adapter managing Polar H10 and Polar Verity Sense connections with link watchdog."""

    def __init__(
        self,
        h10_target: str | None = None,
        sense_target: str | None = None,
        enable_sense_gyro: bool = False,
        enable_sense_mag: bool = False,
        h10_callbacks: dict[str, Callable[[Any], None] | None] | None = None,
        sense_callbacks: dict[str, Callable[[Any], None] | None] | None = None,
        status_callback: Callable[[str, str], None] | None = None,
        enable_watchdog: bool = True,
        watchdog_interval: float = 3.0,
        freeze_timeout: float = 8.0,
        reconnect_cooldown: float = 1.0,
        h10_kwargs: dict[str, Any] | None = None,
        sense_kwargs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self.h10_target = h10_target
        self.sense_target = sense_target
        self.enable_sense_gyro = enable_sense_gyro
        self.enable_sense_mag = enable_sense_mag
        self.raw_h10_callbacks = h10_callbacks or {}
        self.raw_sense_callbacks = sense_callbacks or {}
        self.status_callback = status_callback
        self.enable_watchdog = enable_watchdog
        self.watchdog_interval = watchdog_interval
        self.freeze_timeout = freeze_timeout
        self.reconnect_cooldown = reconnect_cooldown
        self.h10_kwargs = {**kwargs, **(h10_kwargs or {})}
        self.sense_kwargs = {**kwargs, **(sense_kwargs or {})}

        self.h10_dev: Any = None
        self.sense_dev: Any = None
        self.conn_h10: PolarH10 | None = None
        self.conn_sense: PolarVeritySense | None = None

        self._enable_h10_flag = False
        self._enable_sense_flag = False

        self._last_h10_packet_time: float = 0.0
        self._last_sense_packet_time: float = 0.0

        self._reconnecting_h10 = False
        self._reconnecting_sense = False
        self._running = False
        self._watchdog_task: asyncio.Task[None] | None = None

        self.proxy_h10 = _ConnectorProxy(self, "h10")
        self.proxy_sense = _ConnectorProxy(self, "sense")

        # Build wrapped callbacks that update packet arrival timestamps
        self.h10_callbacks: dict[str, Callable[[Any], None]] = {}
        for stream_name, cb in self.raw_h10_callbacks.items():
            if cb is not None:
                self.h10_callbacks[stream_name] = self._wrap_h10_cb(cb)

        self.sense_callbacks: dict[str, Callable[[Any], None]] = {}
        for stream_name, cb in self.raw_sense_callbacks.items():
            if cb is not None:
                self.sense_callbacks[stream_name] = self._wrap_sense_cb(cb)

    @property
    def last_h10_packet_time(self) -> float:
        return self._last_h10_packet_time

    @property
    def last_sense_packet_time(self) -> float:
        return self._last_sense_packet_time

    @property
    def is_h10_connected(self) -> bool:
        if not self.conn_h10:
            return False
        client = getattr(getattr(self.conn_h10, "polar_device", None), "_client", None)
        return bool(client and getattr(client, "is_connected", False))

    @property
    def is_sense_connected(self) -> bool:
        if not self.conn_sense:
            return False
        client = getattr(
            getattr(self.conn_sense, "polar_device", None), "_client", None
        )
        return bool(client and getattr(client, "is_connected", False))

    def _wrap_h10_cb(self, cb: Callable[[Any], None] | None) -> Callable[[Any], None]:
        def wrapped(data: Any) -> None:
            self._last_h10_packet_time = time.monotonic()
            if cb is not None:
                cb(data)

        return wrapped

    def _wrap_sense_cb(self, cb: Callable[[Any], None] | None) -> Callable[[Any], None]:
        def wrapped(data: Any) -> None:
            self._last_sense_packet_time = time.monotonic()
            if cb is not None:
                cb(data)

        return wrapped

    def _init_h10(self) -> None:
        if not self.h10_dev:
            return
        self.conn_h10 = PolarH10(
            self.h10_dev,
            callback=self.h10_callbacks.get("hr"),
            ecg_callback=self.h10_callbacks.get("ecg"),
            acc_callback=self.h10_callbacks.get("acc"),
            verbose=False,
            **self.h10_kwargs,
        )

    def _init_sense(self) -> None:
        if not self.sense_dev:
            return
        # Bandwidth optimization: only pass gyro and mag if explicitly enabled
        gyro_cb = self.sense_callbacks.get("gyro") if self.enable_sense_gyro else None
        mag_cb = self.sense_callbacks.get("mag") if self.enable_sense_mag else None

        self.conn_sense = PolarVeritySense(
            self.sense_dev,
            callback=self.sense_callbacks.get("hr"),
            ppi_callback=self.sense_callbacks.get("ppi"),
            ppg_callback=self.sense_callbacks.get("ppg"),
            acc_callback=self.sense_callbacks.get("acc"),
            gyro_callback=gyro_cb,
            mag_callback=mag_cb,
            verbose=False,
            **self.sense_kwargs,
        )

    async def discover(self, timeout: float = 10.0) -> tuple[Any, Any]:
        """Scan for Polar H10 and Verity Sense devices."""
        h10_dev, sense_dev = await discover_dual_polar_devices(
            self.h10_target, self.sense_target, timeout=timeout
        )
        if h10_dev:
            self.h10_dev = h10_dev
        if sense_dev:
            self.sense_dev = sense_dev
        return h10_dev, sense_dev

    async def connect_and_start_streams(
        self,
        enable_h10: bool = True,
        enable_sense: bool = True,
    ) -> tuple[bool, bool]:
        """Initialize Polar clients and start BLE streaming."""
        self._enable_h10_flag = enable_h10
        self._enable_sense_flag = enable_sense
        self._running = True

        h10_ok = False
        sense_ok = False

        if enable_h10 and self.h10_dev:
            self._init_h10()
            try:
                if self.conn_h10:
                    await self.conn_h10.start_notify()
                    self._last_h10_packet_time = time.monotonic()
                    h10_ok = True
                    logger.info("Polar H10 streaming started successfully.")
            except Exception as e:
                logger.error("Polar H10 start_notify failed: %s", e)
                self.conn_h10 = None

        if enable_sense and self.sense_dev:
            self._init_sense()
            try:
                if self.conn_sense:
                    await self.conn_sense.start_notify()
                    self._last_sense_packet_time = time.monotonic()
                    sense_ok = True
                    opt_str = (
                        " + Gyro/Mag"
                        if (self.enable_sense_gyro or self.enable_sense_mag)
                        else ""
                    )
                    logger.info(
                        "Polar Verity Sense streaming started (PPG + ACC%s).",
                        opt_str,
                    )
            except Exception as e:
                logger.error("Polar Verity Sense start_notify failed: %s", e)
                self.conn_sense = None

        # Start background link watchdog if enabled
        if self.enable_watchdog and (
            self._watchdog_task is None or self._watchdog_task.done()
        ):
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())

        return h10_ok, sense_ok

    async def _watchdog_loop(self) -> None:
        """Periodically check BLE link state and packet arrival times; auto-reconnect on stall."""
        while self._running:
            await asyncio.sleep(self.watchdog_interval)
            now = time.monotonic()

            # Check Sense link
            if self._enable_sense_flag and not self._reconnecting_sense:
                reason: DisconnectReason | None = None
                if self.conn_sense is None:
                    reason = DisconnectReason.LINK_LOSS
                else:
                    client = getattr(
                        getattr(self.conn_sense, "polar_device", None),
                        "_client",
                        None,
                    )
                    is_conn = (
                        getattr(client, "is_connected", False) if client else False
                    )
                    time_since_pkt = (
                        now - self._last_sense_packet_time
                        if self._last_sense_packet_time > 0
                        else 0.0
                    )
                    if not is_conn:
                        reason = DisconnectReason.LINK_LOSS
                    elif (
                        self._last_sense_packet_time > 0
                        and time_since_pkt > self.freeze_timeout
                    ):
                        reason = DisconnectReason.STREAM_FROZEN

                if reason is not None:
                    asyncio.create_task(self._reconnect_sense(reason))

            # Check H10 link
            if self._enable_h10_flag and not self._reconnecting_h10:
                reason = None
                if self.conn_h10 is None:
                    reason = DisconnectReason.LINK_LOSS
                else:
                    client = getattr(
                        getattr(self.conn_h10, "polar_device", None),
                        "_client",
                        None,
                    )
                    is_conn = (
                        getattr(client, "is_connected", False) if client else False
                    )
                    time_since_pkt = (
                        now - self._last_h10_packet_time
                        if self._last_h10_packet_time > 0
                        else 0.0
                    )
                    if not is_conn:
                        reason = DisconnectReason.LINK_LOSS
                    elif (
                        self._last_h10_packet_time > 0
                        and time_since_pkt > self.freeze_timeout
                    ):
                        reason = DisconnectReason.STREAM_FROZEN

                if reason is not None:
                    asyncio.create_task(self._reconnect_h10(reason))

    async def _reconnect_sense(
        self, reason: DisconnectReason = DisconnectReason.LINK_LOSS
    ) -> None:
        """Auto-reconnect handler for Polar Verity Sense."""
        if self._reconnecting_sense or not self._running:
            return
        self._reconnecting_sense = True
        label, guidance = DISCONNECT_INFO[reason]
        if self.status_callback:
            self.status_callback("Sense", f"Watchdog: {label.lower()}; reconnecting...")
        logger.warning("Polar Sense %s: %s", label.lower(), guidance)

        try:
            if self.conn_sense:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(self.conn_sense.stop_notify(), timeout=3.0)
            await asyncio.sleep(self.reconnect_cooldown)
            if not self.sense_dev:
                _, fresh_dev = await self.discover(timeout=5.0)
                if fresh_dev:
                    self.sense_dev = fresh_dev
            if self.sense_dev:
                self._init_sense()
                if self.conn_sense:
                    await self.conn_sense.start_notify()
                    self._last_sense_packet_time = time.monotonic()
                    if self.status_callback:
                        self.status_callback("Sense", "Connected! Streaming...")
                    logger.info("Polar Sense reconnected and resumed streaming.")
        except Exception as exc:
            fail_label, fail_guidance = DISCONNECT_INFO[
                (
                    DisconnectReason.BOND_BROKEN
                    if looks_like_bond_break(str(exc))
                    else DisconnectReason.LINK_LOSS
                )
            ]
            logger.error(
                "Polar Sense reconnect failed (%s): %s — %s",
                fail_label.lower(),
                exc,
                fail_guidance,
            )
            if self.status_callback:
                self.status_callback("Sense", f"{fail_label}: {fail_guidance}")
        finally:
            self._reconnecting_sense = False

    async def _reconnect_h10(
        self, reason: DisconnectReason = DisconnectReason.LINK_LOSS
    ) -> None:
        """Auto-reconnect handler for Polar H10."""
        if self._reconnecting_h10 or not self._running:
            return
        self._reconnecting_h10 = True
        label, guidance = DISCONNECT_INFO[reason]
        if self.status_callback:
            self.status_callback("H10", f"Watchdog: {label.lower()}; reconnecting...")
        logger.warning("Polar H10 %s: %s", label.lower(), guidance)

        try:
            if self.conn_h10:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(self.conn_h10.stop_notify(), timeout=3.0)
            await asyncio.sleep(self.reconnect_cooldown)
            if not self.h10_dev:
                fresh_dev, _ = await self.discover(timeout=5.0)
                if fresh_dev:
                    self.h10_dev = fresh_dev
            if self.h10_dev:
                self._init_h10()
                if self.conn_h10:
                    await self.conn_h10.start_notify()
                    self._last_h10_packet_time = time.monotonic()
                    if self.status_callback:
                        self.status_callback("H10", "Connected! Streaming...")
                    logger.info("Polar H10 reconnected and resumed streaming.")
        except Exception as exc:
            fail_label, fail_guidance = DISCONNECT_INFO[
                (
                    DisconnectReason.BOND_BROKEN
                    if looks_like_bond_break(str(exc))
                    else DisconnectReason.LINK_LOSS
                )
            ]
            logger.error(
                "Polar H10 reconnect failed (%s): %s — %s",
                fail_label.lower(),
                exc,
                fail_guidance,
            )
            if self.status_callback:
                self.status_callback("H10", f"{fail_label}: {fail_guidance}")
        finally:
            self._reconnecting_h10 = False

    async def disconnect(self) -> None:
        """Stop notifications and disconnect all Polar devices."""
        self._running = False
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watchdog_task
        self._watchdog_task = None

        for label, conn in [("H10", self.conn_h10), ("Sense", self.conn_sense)]:
            if conn:
                try:
                    await asyncio.wait_for(conn.stop_notify(), timeout=5.0)
                except Exception as e:
                    logger.debug("Polar %s disconnect error: %s", label, e)
        self.conn_h10 = None
        self.conn_sense = None
