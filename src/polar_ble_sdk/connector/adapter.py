"""Polar BLE device adapter for Polar H10 and Verity Sense with auto-reconnect watchdog."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .ble_discovery import discover_dual_polar_devices, discover_polar_device
from .stream import PolarH10, PolarVeritySense
from .stream.base import DISCONNECT_INFO, DisconnectReason, looks_like_bond_break

logger = logging.getLogger("polar_adapter")


@dataclass
class _Link:
    """One device's side of the adapter: its target, live connector and health.

    A link is also the stable handle callers hold on to: ``polar_device`` and
    ``stream_errors`` follow the connector across reconnects, which replaces the
    connector itself when the watchdog rebuilds it.
    """

    key: str  # "h10" | "sense"
    label: str  # human-readable, used in status messages
    target: str | None
    factory: Callable[..., Any]
    kwargs: dict[str, Any] = field(default_factory=dict)
    callbacks: dict[str, Callable[[Any], None]] = field(default_factory=dict)
    dev: Any = None
    conn: Any = None
    enabled: bool = False
    reconnecting: bool = False
    last_packet_time: float = 0.0

    @property
    def polar_device(self) -> Any:
        return getattr(self.conn, "polar_device", None)

    @property
    def stream_errors(self) -> dict[str, str]:
        return getattr(self.conn, "stream_errors", {})

    @property
    def client(self) -> Any:
        return getattr(self.polar_device, "_client", None)

    @property
    def is_connected(self) -> bool:
        client = self.client
        return bool(client and getattr(client, "is_connected", False))

    def wrap(self, cb: Callable[[Any], None]) -> Callable[[Any], None]:
        """Tag every delivered packet with its arrival time, for the watchdog."""

        def wrapped(data: Any) -> None:
            self.last_packet_time = time.monotonic()
            cb(data)

        return wrapped

    def build(self) -> None:
        """(Re)create the connector for this link from the current callbacks."""
        if not self.dev:
            return
        cb_kwargs = {
            ("callback" if stream == "hr" else f"{stream}_callback"): cb
            for stream, cb in self.callbacks.items()
        }
        self.conn = self.factory(self.dev, verbose=False, **cb_kwargs, **self.kwargs)

    def stall_reason(
        self, now: float, freeze_timeout: float
    ) -> DisconnectReason | None:
        """Why this link needs re-establishing, or None while it is healthy."""
        if self.conn is None or not self.is_connected:
            return DisconnectReason.LINK_LOSS
        if self.last_packet_time > 0 and (now - self.last_packet_time) > freeze_timeout:
            return DisconnectReason.STREAM_FROZEN
        return None


class PolarAdapter:
    """Adapter managing Polar H10 and Polar Verity Sense connections with link watchdog."""

    def __init__(
        self,
        h10_target: str | None = None,
        sense_target: str | None = None,
        enable_sense_gyro: bool = False,
        enable_sense_mag: bool = False,
        h10_callbacks: Mapping[str, Callable[[Any], None] | None] | None = None,
        sense_callbacks: Mapping[str, Callable[[Any], None] | None] | None = None,
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
        self.status_callback = status_callback
        self.enable_watchdog = enable_watchdog
        self.watchdog_interval = watchdog_interval
        self.freeze_timeout = freeze_timeout
        self.reconnect_cooldown = reconnect_cooldown

        # Bandwidth optimization: ignore gyro/mag callbacks unless asked for.
        disabled = {"gyro"} if not enable_sense_gyro else set()
        if not enable_sense_mag:
            disabled.add("mag")

        self.h10 = _Link(
            key="h10",
            label="H10",
            target=h10_target,
            factory=PolarH10,
            kwargs={**kwargs, **(h10_kwargs or {})},
        )
        self.sense = _Link(
            key="sense",
            label="Sense",
            target=sense_target,
            factory=PolarVeritySense,
            kwargs={**kwargs, **(sense_kwargs or {})},
        )
        self.links: dict[str, _Link] = {"h10": self.h10, "sense": self.sense}

        for link, raw in ((self.h10, h10_callbacks), (self.sense, sense_callbacks)):
            link.callbacks = {
                stream: link.wrap(cb)
                for stream, cb in (raw or {}).items()
                if cb is not None and not (link is self.sense and stream in disabled)
            }

        self._running = False
        self._watchdog_task: asyncio.Task[None] | None = None
        self._active_tasks: set[asyncio.Task[Any]] = set()

    def _create_task(self, coro: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro)
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)
        return task

    async def discover(self, timeout: float = 10.0) -> tuple[Any, Any]:
        """Scan for Polar H10 and Verity Sense devices."""
        h10_dev, sense_dev = await discover_dual_polar_devices(
            self.h10_target, self.sense_target, timeout=timeout
        )
        if h10_dev:
            self.h10.dev = h10_dev
        if sense_dev:
            self.sense.dev = sense_dev
        return h10_dev, sense_dev

    async def connect_and_start_streams(
        self,
        enable_h10: bool = True,
        enable_sense: bool = True,
    ) -> tuple[bool, bool]:
        """Initialize Polar clients and start BLE streaming."""
        self._running = True
        self.h10.enabled = enable_h10
        self.sense.enabled = enable_sense

        results = []
        for link in (self.h10, self.sense):
            results.append(link.enabled and bool(link.dev) and await self._start(link))

        if self.enable_watchdog and (
            self._watchdog_task is None or self._watchdog_task.done()
        ):
            self._watchdog_task = self._create_task(self._watchdog_loop())

        return results[0], results[1]

    async def _start(self, link: _Link) -> bool:
        """Build the connector and subscribe; False if the device refused."""
        link.build()
        if not link.conn:
            return False
        try:
            await link.conn.start_notify()
        except Exception as e:
            logger.error("Polar %s start_notify failed: %s", link.label, e)
            link.conn = None
            return False
        link.last_packet_time = time.monotonic()
        logger.info("Polar %s streaming started successfully.", link.label)
        return True

    async def _watchdog_loop(self) -> None:
        """Periodically check BLE link state and packet arrival times; auto-reconnect on stall."""
        while self._running:
            await asyncio.sleep(self.watchdog_interval)
            now = time.monotonic()
            for link in self.links.values():
                if not link.enabled or link.reconnecting:
                    continue
                reason = link.stall_reason(now, self.freeze_timeout)
                if reason is not None:
                    self._create_task(self._reconnect(link, reason))

    async def _reconnect(
        self, link: _Link, reason: DisconnectReason = DisconnectReason.LINK_LOSS
    ) -> None:
        """Tear the link down and bring it back up after a loss or a freeze."""
        if link.reconnecting or not self._running:
            return
        link.reconnecting = True
        label, guidance = DISCONNECT_INFO[reason]
        self._notify(link, f"Watchdog: {label.lower()}; reconnecting...")
        logger.warning("Polar %s %s: %s", link.label, label.lower(), guidance)

        try:
            if link.conn:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(link.conn.stop_notify(), timeout=3.0)
            await asyncio.sleep(self.reconnect_cooldown)
            if not link.dev:
                link.dev = await discover_polar_device(
                    link.target or link.key, timeout=5.0
                )
            if link.dev:
                link.build()
                if link.conn:
                    await link.conn.start_notify()
                    link.last_packet_time = time.monotonic()
                    self._notify(link, "Connected! Streaming...")
                    logger.info(
                        "Polar %s reconnected and resumed streaming.", link.label
                    )
        except Exception as exc:
            fail_label, fail_guidance = DISCONNECT_INFO[
                (
                    DisconnectReason.BOND_BROKEN
                    if looks_like_bond_break(str(exc))
                    else DisconnectReason.LINK_LOSS
                )
            ]
            logger.error(
                "Polar %s reconnect failed (%s): %s — %s",
                link.label,
                fail_label.lower(),
                exc,
                fail_guidance,
            )
            self._notify(link, f"{fail_label}: {fail_guidance}")
        finally:
            link.reconnecting = False

    def _notify(self, link: _Link, msg: str) -> None:
        if self.status_callback:
            self.status_callback(link.label, msg)

    async def disconnect(self) -> None:
        """Stop notifications and disconnect all Polar devices."""
        self._running = False
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watchdog_task
        self._watchdog_task = None

        for t in list(self._active_tasks):
            t.cancel()
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
        self._active_tasks.clear()

        for link in self.links.values():
            if link.conn:
                try:
                    await asyncio.wait_for(link.conn.stop_notify(), timeout=5.0)
                except Exception as e:
                    logger.debug("Polar %s disconnect error: %s", link.label, e)
            link.conn = None
