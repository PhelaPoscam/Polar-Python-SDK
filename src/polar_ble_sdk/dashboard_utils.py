"""Backward-compatibility façade re-exporting modular SDK components.

All functionality previously in this module has been decomposed into specialized packages:
    - ``polar_ble_sdk.storage``: File I/O, summary CSV, and full-resolution frame loggers.
    - ``polar_ble_sdk.metrics``: Physiological calculations (RMSSD, SDNN) and sampling rate trackers.
    - ``polar_ble_sdk.session``: Session metadata manifests (``session_meta.json``) and device state models.
    - ``polar_ble_sdk.diagnostics``: Battery telemetry and BLE RSSI monitoring.
    - ``polar_ble_sdk.ui``: Rich terminal layout, device panels, and rolling event logs.
    - ``polar_ble_sdk.input``: Non-blocking hotkey and marker ingestion.

This module re-exports all legacy symbols to ensure 100% backward compatibility.
"""

from __future__ import annotations

# ── Diagnostics (Battery & RSSI) ──────────────────────────────────────────
from .diagnostics.battery import (
    BATTERY_SERVICE_UUID,
    read_battery,
    update_battery_loop,
)
from .diagnostics.rssi import (
    FrameCountLogger,
    read_rssi,
    rssi_loop,
)

# ── Input (Keyboard & Markers) ───────────────────────────────────────────
from .input.keyboard import (
    NonBlockingKeyboardReader,
    format_marker_legend,
    parse_marker_specs,
)

# ── Metrics (HRV & Rate Tracking) ─────────────────────────────────────────
from .metrics.hrv import (
    calculate_pnn50,
    calculate_rmssd,
    calculate_sdnn,
)
from .metrics.rate_tracker import (
    RateTracker,
    RateVerificationResult,
    StreamAccumulator,
    compute_session_hz,
    print_hz_summary,
    update_hz_for_state,
)

# ── Session & State ───────────────────────────────────────────────────────
from .session.session import (
    DeviceMetadata,
    SessionManager,
    SessionMetadata,
)
from .session.state import (
    _track_session,
    feed_acc,
    feed_ecg,
    feed_gyro,
    feed_hr,
    feed_mag,
    feed_ppg,
    feed_ppi,
    make_callback,
    make_device_state,
    unwrap_vector,
)

# ── Storage (CSV & Frame Loggers) ─────────────────────────────────────────
from .storage.frame_logger import (
    StreamFrameLogger,
    make_frame_callback,
    make_hr_callback,
    make_ppi_callback,
)
from .storage.summary_logger import CsvLogger

# ── UI (Rich Panels & Logs) ───────────────────────────────────────────────
from .ui.components import (
    device_panel,
    header_bar,
    info_bar,
)
from .ui.log_panel import (
    SEVERITY_ICONS,
    SEVERITY_STYLES,
    LogPanel,
    log_event,
)

_read_rssi = read_rssi

__all__ = [
    # UI
    "SEVERITY_ICONS",
    "SEVERITY_STYLES",
    "LogPanel",
    "log_event",
    "device_panel",
    "header_bar",
    "info_bar",
    # Diagnostics
    "BATTERY_SERVICE_UUID",
    "read_battery",
    "update_battery_loop",
    "_read_rssi",
    "read_rssi",
    "rssi_loop",
    "FrameCountLogger",
    # State & Session
    "make_device_state",
    "unwrap_vector",
    "_track_session",
    "feed_hr",
    "feed_ppg",
    "feed_acc",
    "feed_gyro",
    "feed_mag",
    "feed_ecg",
    "feed_ppi",
    "make_callback",
    "DeviceMetadata",
    "SessionMetadata",
    "SessionManager",
    # Storage
    "CsvLogger",
    "StreamFrameLogger",
    "make_frame_callback",
    "make_ppi_callback",
    "make_hr_callback",
    # Metrics
    "calculate_rmssd",
    "calculate_sdnn",
    "calculate_pnn50",
    "update_hz_for_state",
    "compute_session_hz",
    "print_hz_summary",
    "RateTracker",
    "StreamAccumulator",
    "RateVerificationResult",
    # Input
    "NonBlockingKeyboardReader",
    "parse_marker_specs",
    "format_marker_legend",
]
