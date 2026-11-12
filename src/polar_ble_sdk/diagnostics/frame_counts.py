"""Per-stream frame count deltas for the verbose event log.

There is no RSSI readout: bleak 3.x exposes RSSI only in scan advertisements,
not on a connected client.
"""

from __future__ import annotations

from typing import Any


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
