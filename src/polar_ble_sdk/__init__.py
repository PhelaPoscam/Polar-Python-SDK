"""Polar BLE Python SDK package.

An open-source Python SDK for connecting, monitoring, and capturing raw physiological
and IMU data from Polar BLE devices (H10, Verity Sense, Vantage/Grit watches).

Research helpers (``polar_ble_sdk.research``) need the optional research extras
(pandas, numpy, scipy, matplotlib) and are imported from that subpackage directly.
"""

from typing import Any

from polar_ble_sdk.connector.adapter import PolarAdapter
from polar_ble_sdk.connector.ble_discovery import (
    discover_dual_polar_devices,
    discover_polar_device,
    discover_polar_devices,
)
from polar_ble_sdk.connector.stream import create_polar_connector
from polar_ble_sdk.lsl.bridge import PolarLSLBridge
from polar_ble_sdk.metrics.hrv import (
    calculate_pnn50,
    calculate_rmssd,
    calculate_sdnn,
)
from polar_ble_sdk.session.session import (
    DeviceMetadata,
    SessionManager,
    SessionMetadata,
)

_LAZY_RESEARCH_SYMBOLS = {
    "load_session": "polar_ble_sdk.research.loader",
    "PolarSessionData": "polar_ble_sdk.research.loader",
    "verify_session_integrity": "polar_ble_sdk.research.audit",
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_RESEARCH_SYMBOLS:
        mod_name = _LAZY_RESEARCH_SYMBOLS[name]
        try:
            import importlib

            mod = importlib.import_module(mod_name)
            val = getattr(mod, name)
            globals()[name] = val
            return val
        except ImportError as e:
            raise ImportError(
                f"'{name}' requires the research dependencies (pandas, numpy, scipy). "
                "Install them with: pip install 'polar-ble-sdk[research]'"
            ) from e
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    # Discovery & Connection
    "discover_polar_device",
    "discover_dual_polar_devices",
    "discover_polar_devices",
    "create_polar_connector",
    "PolarAdapter",
    "PolarLSLBridge",
    # Data Models
    "DeviceMetadata",
    "SessionMetadata",
    "SessionManager",
    # Metrics
    "calculate_rmssd",
    "calculate_sdnn",
    "calculate_pnn50",
    # Research & Audit (Lazy Loaded)
    "load_session",
    "verify_session_integrity",
    "PolarSessionData",
]
