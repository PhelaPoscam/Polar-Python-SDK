"""BLE signal strength (RSSI) telemetry and frame count delta tracking."""

from __future__ import annotations

import asyncio
from typing import Any


async def read_rssi(client: Any) -> int | None:
    """Read RSSI from a BleakClient across public and backend implementations."""
    if not client:
        return None
    if hasattr(client, "get_rssi"):
        try:
            return await client.get_rssi()
        except Exception:
            pass
    backend = getattr(client, "_backend", None)
    if backend and hasattr(backend, "_notification_callbacks"):
        ble_device = getattr(client, "_device", None)
        if ble_device and hasattr(ble_device, "rssi"):
            return ble_device.rssi
    return None


async def rssi_loop(
    conn: Any,
    log_panel: Any,
    *,
    device: str = "",
    log_file: Any = None,
) -> None:
    """Periodically read RSSI and emit events to the rolling log panel."""
    from ..ui.log_panel import log_event

    client = (
        getattr(conn.polar_device, "_client", None)
        if conn and conn.polar_device
        else None
    )
    if not client:
        return

    rssi = await read_rssi(client)
    if rssi is None:
        log_event(
            log_panel,
            "RSSI not available (bleak 3.x backend restriction)",
            "warning",
            device=device,
            log_file=log_file,
        )
        return

    log_event(
        log_panel,
        f"RSSI: {rssi} dBm",
        "info",
        device=device,
        log_file=log_file,
    )
    while True:
        interval = 5.0 if getattr(log_panel, "level", "moderate") == "verbose" else 30.0
        await asyncio.sleep(interval)
        try:
            rssi = await read_rssi(client)
            if rssi is not None:
                log_event(
                    log_panel,
                    f"RSSI: {rssi} dBm",
                    "info",
                    device=device,
                    log_file=log_file,
                )
        except Exception:
            pass


class FrameCountLogger:
    """Tracks per-stream frame count deltas and emits verbose log events."""

    def __init__(
        self,
        log_panel: Any,
        *,
        device: str = "",
        log_file: Any = None,
    ) -> None:
        self._log_panel = log_panel
        self._device = device
        self._log_file = log_file
        self._prev: dict[str, int] = {}

    def check(self, state: dict[str, Any], enabled_streams: list[str]) -> None:
        """Compare current counts to previous, logging deltas for active streams."""
        from ..ui.log_panel import log_event

        stream_count_keys = {
            "ecg": "ecg_count",
            "ppg": "ppg_count",
            "acc": "acc_count",
            "gyro": "gyro_count",
            "mag": "mag_count",
            "ppi": "ppi_count",
            "hr": None,
        }
        for stream in enabled_streams:
            key = stream_count_keys.get(stream)
            if key is None:
                continue
            current = state.get(key, 0)
            if stream not in self._prev:
                self._prev[stream] = current
                continue
            prev = self._prev[stream]
            delta = current - prev
            if delta > 0:
                log_event(
                    self._log_panel,
                    f"{stream.upper()} +{delta} frames",
                    "info",
                    device=self._device,
                    log_file=self._log_file,
                )
            self._prev[stream] = current
