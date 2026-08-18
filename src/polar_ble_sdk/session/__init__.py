"""Session package for metadata management, provenance manifests, and in-memory state."""

from .session import (
    DeviceMetadata,
    SessionManager,
    SessionMetadata,
)
from .state import (
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

__all__ = [
    "DeviceMetadata",
    "SessionMetadata",
    "SessionManager",
    "make_device_state",
    "unwrap_vector",
    "feed_hr",
    "feed_ppg",
    "feed_acc",
    "feed_gyro",
    "feed_mag",
    "feed_ecg",
    "feed_ppi",
    "make_callback",
]
