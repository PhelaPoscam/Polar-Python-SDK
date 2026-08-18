"""Research-grade session management, metadata tracking, and audit manifests.

Ensures every recording session writes standardized provenance metadata (ISO-8601 UTC
timestamps, Unix epoch nanoseconds, hardware MAC, firmware parameters, stream configs,
and data integrity stats) to ``session_meta.json``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import platform
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..metrics.rate_tracker import RateTracker, RateVerificationResult
from ..storage.frame_logger import StreamFrameLogger

logger = logging.getLogger(__name__)

MANIFEST_SCHEMA_VERSION = "1.0.0"


@dataclass
class DeviceMetadata:
    """Metadata describing a physical Polar BLE sensor."""

    name: str = ""
    address: str = ""
    device_type: str = "unknown"
    battery_start: str = "-"
    battery_end: str = "-"
    features_detected: list[str] = field(default_factory=list)
    stream_configurations: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionMetadata:
    """Complete provenance and audit manifest for a recording session."""

    schema_version: str = MANIFEST_SCHEMA_VERSION
    session_id: str = ""
    session_type: str = "single"  # "single" | "dual"
    start_time_iso: str = ""
    start_time_epoch_ns: int = 0
    end_time_iso: str = ""
    end_time_epoch_ns: int = 0
    duration_s: float = 0.0
    system_info: dict[str, str] = field(default_factory=dict)
    devices: dict[str, DeviceMetadata] = field(default_factory=dict)
    stream_results: dict[str, Any] = field(default_factory=dict)
    markers: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


class SessionManager:
    """Orchestrates recording directories, log files, CSV loggers, and audit manifests."""

    def __init__(
        self,
        base_dir: Path | str,
        device_type: str,
        session_id: str | None = None,
        *,
        is_dual: bool = False,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.device_type = device_type
        self.is_dual = is_dual
        self.session_id = session_id or time.strftime("%Y%m%d_%H%M%S")

        # Root session folder: e.g. data/h10/20260818_120000 or data/dual/20260818_120000
        self.session_dir = self.base_dir / "data" / self.device_type / self.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Metadata structure
        now_dt = datetime.now(timezone.utc)
        self.metadata = SessionMetadata(
            session_id=self.session_id,
            session_type="dual" if is_dual else "single",
            start_time_iso=now_dt.isoformat(),
            start_time_epoch_ns=time.time_ns(),
            system_info={
                "os": platform.platform(),
                "python_version": sys.version.split()[0],
                "platform": sys.platform,
            },
        )

        self._log_file: Any = None
        self._frame_loggers: dict[str, StreamFrameLogger] = {}

    def init_event_log(self, prefix: str = "monitor") -> Path:
        """Create and open the plain-text session event log file."""
        log_path = self.session_dir / f"{prefix}_{self.session_id}.log"
        try:
            self._log_file = log_path.open("w", encoding="utf-8")
        except OSError as e:
            logger.warning("Could not open event log file %s: %s", log_path, e)
            self._log_file = None
        return log_path

    @property
    def log_file(self) -> Any:
        return self._log_file

    def get_raw_dir(self, sub_device: str | None = None) -> Path:
        """Get the raw CSV directory, optionally nested for dual devices."""
        raw_dir = (
            self.session_dir / sub_device / "raw"
            if sub_device
            else self.session_dir / "raw"
        )
        raw_dir.mkdir(parents=True, exist_ok=True)
        return raw_dir

    def get_post_processed_dir(self, sub_device: str | None = None) -> Path:
        """Get the post-processed summary CSV directory."""
        pp_dir = (
            self.session_dir / sub_device / "post-processed"
            if sub_device
            else self.session_dir / "post-processed"
        )
        pp_dir.mkdir(parents=True, exist_ok=True)
        return pp_dir

    def create_frame_logger(
        self, stream: str, sub_device: str | None = None
    ) -> StreamFrameLogger:
        """Instantiate and open a StreamFrameLogger inside the raw directory."""
        raw_dir = self.get_raw_dir(sub_device)
        logger_key = f"{sub_device}_{stream}" if sub_device else stream
        frame_logger = StreamFrameLogger(raw_dir / f"{stream}.csv", stream)
        frame_logger.open()
        self._frame_loggers[logger_key] = frame_logger
        return frame_logger

    def register_marker(self, label: str, timestamp_s: float | None = None) -> None:
        """Record an event marker in the session metadata."""
        now = time.time() if timestamp_s is None else timestamp_s
        self.metadata.markers.append(
            {
                "timestamp_iso": datetime.now(timezone.utc).isoformat(),
                "timestamp_epoch_s": now,
                "label": label,
            }
        )

    def close_all(
        self,
        rate_tracker: RateTracker | None = None,
        configured_rates: dict[str, int] | None = None,
    ) -> None:
        """Flush and close all open frame loggers, event logs, and write session_meta.json."""
        for fl in self._frame_loggers.values():
            fl.close()

        if self._log_file:
            with contextlib.suppress(OSError):
                self._log_file.close()
            self._log_file = None

        # Finalize metadata
        now_dt = datetime.now(timezone.utc)
        self.metadata.end_time_iso = now_dt.isoformat()
        self.metadata.end_time_epoch_ns = time.time_ns()
        self.metadata.duration_s = (
            self.metadata.end_time_epoch_ns - self.metadata.start_time_epoch_ns
        ) / 1e9

        if rate_tracker and configured_rates:
            results: list[RateVerificationResult] = rate_tracker.verify_all(
                configured_rates
            )
            for r in results:
                self.metadata.stream_results[r.stream] = asdict(r)

        # Write session_meta.json
        meta_path = self.session_dir / "session_meta.json"
        try:
            with meta_path.open("w", encoding="utf-8") as f:
                f.write(self.metadata.to_json(indent=2))
        except OSError as e:
            logger.warning("Could not write session manifest to %s: %s", meta_path, e)
