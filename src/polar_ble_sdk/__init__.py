"""Polar BLE Python SDK package."""

from __future__ import annotations

from polar_ble_sdk.connector.ble_discovery import (
    discover_dual_polar_devices,
    discover_polar_device,
)
from polar_ble_sdk.connector.schemas import SignalPacket
from polar_ble_sdk.connector.stream import create_polar_connector
from polar_ble_sdk.reader import StressPredictor, load_model_bundle
from polar_ble_sdk.reader.realtime import ReaderConfig, run_reader

__all__ = [
    "discover_polar_device",
    "discover_dual_polar_devices",
    "create_polar_connector",
    "StressPredictor",
    "load_model_bundle",
    "ReaderConfig",
    "run_reader",
    "SignalPacket",
]
