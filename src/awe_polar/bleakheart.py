"""Lightweight helper to handle BLE Heart Rate notifications.

This provides a minimal compatible `HeartRate` class used by the app to
start/stop notifications from the standard Heart Rate Measurement characteristic
(00002a37-0000-1000-8000-00805f9b34fb) and call a provided callback with the
parsed heart rate (integer BPM).

It's intentionally small and dependency-free (uses Bleak client passed-in by
the app) so you don't need an external `bleakheart` package on PyPI.
"""
from __future__ import annotations

from typing import Callable, Optional

HEART_RATE_CHAR = "00002a37-0000-1000-8000-00805f9b34fb"


class HeartRate:
    """Simple wrapper around a Bleak client to receive HR notifications.

    Usage:
        heartrate = HeartRate(client, callback=print_hr_data)
        await heartrate.start_notify()
        await heartrate.stop_notify()
    """

    def __init__(self, client, callback: Optional[Callable] = None, instant_rate: bool = True, unpack: bool = True):
        self.client = client
        self.callback = callback
        self.instant_rate = instant_rate
        self.unpack = unpack
        self._running = False

    async def start_notify(self) -> None:
        """Begin listening to HR notifications on the standard characteristic."""
        await self.client.start_notify(HEART_RATE_CHAR, self._notification_handler)
        self._running = True

    async def stop_notify(self) -> None:
        """Stop listening to HR notifications."""
        if self._running:
            await self.client.stop_notify(HEART_RATE_CHAR)
            self._running = False

    def _notification_handler(self, sender, data: bytes) -> None:
        """Parse Heart Rate Measurement characteristic bytes and call callback.

        The HR characteristic follows Bluetooth SIG specification. Flags in the
        first byte determine whether HR is 8-bit or 16-bit. This handler only
        extracts the current HR value and forwards it to the callback.
        """
        if not data:
            return

        flags = data[0]
        hr_format = flags & 0x01

        try:
            if hr_format == 0:
                hr_value = data[1]
            else:
                hr_value = int.from_bytes(data[1:3], "little")
        except Exception:
            return

        if self.callback:
            try:
                if self.unpack:
                    self.callback(hr_value)
                else:
                    self.callback({"hr": hr_value, "raw": data})
            except Exception:
                # Keep notifications robust by swallowing callback errors
                return
