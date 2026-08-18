"""Diagnostics package for battery monitoring and BLE RSSI telemetry."""

from .battery import BATTERY_SERVICE_UUID, read_battery, update_battery_loop
from .rssi import FrameCountLogger, read_rssi, rssi_loop

__all__ = [
    "BATTERY_SERVICE_UUID",
    "read_battery",
    "update_battery_loop",
    "read_rssi",
    "rssi_loop",
    "FrameCountLogger",
]
