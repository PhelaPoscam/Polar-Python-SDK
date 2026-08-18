"""Polar BLE Python SDK package.

An open-source Python SDK for connecting, monitoring, and capturing raw physiological
and IMU data from Polar BLE devices (H10, Verity Sense, Vantage/Grit watches).
"""

from __future__ import annotations

from polar_ble_sdk.connector.ble_discovery import (
    discover_dual_polar_devices,
    discover_polar_device,
    discover_polar_devices,
)
from polar_ble_sdk.connector.schemas import SignalPacket
from polar_ble_sdk.connector.stream import create_polar_connector
from polar_ble_sdk.metrics.hrv import (
    calculate_pnn50,
    calculate_rmssd,
    calculate_sdnn,
)
from polar_ble_sdk.research.audit import verify_session_integrity
from polar_ble_sdk.research.loader import PolarSessionData, load_session
from polar_ble_sdk.session.session import (
    DeviceMetadata,
    SessionManager,
    SessionMetadata,
)

__all__ = [
    # Discovery & Connection
    "discover_polar_device",
    "discover_dual_polar_devices",
    "discover_polar_devices",
    "create_polar_connector",
    # Data Models
    "SignalPacket",
    "DeviceMetadata",
    "SessionMetadata",
    "SessionManager",
    # Metrics
    "calculate_rmssd",
    "calculate_sdnn",
    "calculate_pnn50",
    # Research & Audit
    "load_session",
    "verify_session_integrity",
    "PolarSessionData",
]
