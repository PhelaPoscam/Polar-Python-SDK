"""High-frequency, full-resolution per-stream raw CSV logging.

Records each individual sensor packet delivered by Polar PMD or Heart Rate characteristics
with millisecond-accurate timestamps relative to the first received frame.
"""

from __future__ import annotations

import csv
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class StreamFrameLogger:
    """Writes raw PMD, HR, and PPI frames to a designated CSV file.

    Stream Columns Reference:
        - ``ecg``: ``Timestamp_s, uV_Samples`` (Microvolts)
        - ``ppg``: ``Timestamp_s, Sample_Channels`` (Raw 22-bit ADC counts)
        - ``acc``: ``Timestamp_s, X_mG, Y_mG, Z_mG`` (Milli-g acceleration)
        - ``gyro``: ``Timestamp_s, X_dps, Y_dps, Z_dps`` (Degrees per second)
        - ``mag``: ``Timestamp_s, X_G, Y_G, Z_G`` (Gauss magnetic field)
        - ``hr``: ``Timestamp_s, HeartRate_BPM, RR_Intervals_ms`` (BPM & ms intervals)
        - ``ppi``: ``Timestamp_s, PPI_ms, ErrEst_ms, HR_BPM, SkinContact, SkinContactSupported``
    """

    _COLUMNS: ClassVar[dict[str, list[str]]] = {
        "ecg": ["Timestamp_s", "uV_Samples"],
        "ppg": ["Timestamp_s", "Sample_Channels"],
        "acc": ["Timestamp_s", "X_mG", "Y_mG", "Z_mG"],
        "gyro": ["Timestamp_s", "X_dps", "Y_dps", "Z_dps"],
        "mag": ["Timestamp_s", "X_G", "Y_G", "Z_G"],
        "hr": ["Timestamp_s", "HeartRate_BPM", "RR_Intervals_ms"],
        "ppi": [
            "Timestamp_s",
            "PPI_ms",
            "ErrEst_ms",
            "HR_BPM",
            "SkinContact",
            "SkinContactSupported",
        ],
    }

    _WIDE_COLUMNS: ClassVar[set[str]] = {"ecg", "ppg"}

    def __init__(self, path: Path | str, stream: str) -> None:
        self._path = Path(path)
        self._stream = stream.lower()
        self._writer: Any = None
        self._file: Any = None
        self._first_ts_ns: int | None = None
        self._ppi_cumulative_s: float = 0.0
        self.samples_written = 0

    def open(self) -> None:
        """Open the file and write the CSV header."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self._path.open("w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(self._COLUMNS.get(self._stream, ["Timestamp_s", "Data"]))

    def write_frame(self, timestamp_ns: int, data: Any) -> None:
        """Write a single frame of data with relative timestamp."""
        if not self._writer:
            return

        if self._first_ts_ns is None:
            self._first_ts_ns = timestamp_ns

        rel_s = (timestamp_ns - self._first_ts_ns) / 1e9

        if self._stream == "hr":
            hr_val, rr_list = data
            rr_str = ";".join(f"{rr:.1f}" for rr in rr_list) if rr_list else ""
            self._writer.writerow([f"{rel_s:.3f}", hr_val, rr_str])
            self.samples_written += 1
        elif self._stream in self._WIDE_COLUMNS:
            self._writer.writerow([f"{rel_s:.3f}", *data])
            self.samples_written += len(data)
        else:
            for sample in data:
                self._writer.writerow([f"{rel_s:.3f}", *sample])
                self.samples_written += 1

    def write_ppi_frames(self, data: list[Any]) -> None:
        """Write a batch of PPI samples with quality and skin-contact flags."""
        if not self._writer:
            return

        for sample in data:
            if len(sample) >= 4:
                ppi = sample[1]
                err_est = sample[2]
                hr = sample[3]
                contact = sample[4] if len(sample) >= 5 else None
                contact_sup = sample[5] if len(sample) >= 6 else None
            else:
                ppi = sample[1]
                err_est = hr = contact = contact_sup = None

            self._writer.writerow(
                [
                    f"{self._ppi_cumulative_s:.3f}",
                    ppi,
                    "" if err_est is None else err_est,
                    "" if hr is None else hr,
                    "" if contact is None else int(bool(contact)),
                    "" if contact_sup is None else int(bool(contact_sup)),
                ]
            )
            self._ppi_cumulative_s += float(ppi) / 1000.0
            self.samples_written += 1

    def close(self) -> None:
        """Flush and close the underlying file handle."""
        if self._file:
            try:
                self._file.close()
            except OSError as e:
                logger.warning("Error closing frame log file %s: %s", self._path, e)
            finally:
                self._file = None
                self._writer = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def path_str(self) -> str:
        return str(self._path)


def make_frame_callback(
    dashboard_cb: Callable[[Any], None],
    frame_logger: StreamFrameLogger,
) -> Callable[[Any], None]:
    """Wrap a dashboard callback to simultaneously write high-resolution frames."""

    def cb(data: Any) -> None:
        dashboard_cb(data)
        timestamp, samples = data
        frame_logger.write_frame(timestamp, samples)

    return cb


def make_ppi_callback(
    dashboard_cb: Callable[[Any], None],
    frame_logger: StreamFrameLogger,
) -> Callable[[Any], None]:
    """Wrap a PPI callback to simultaneously write high-resolution frames."""

    def cb(data: Any) -> None:
        dashboard_cb(data)
        frame_logger.write_ppi_frames(data)

    return cb


def make_hr_callback(
    dashboard_cb: Callable[[Any], None],
    frame_logger: StreamFrameLogger,
) -> Callable[[Any], None]:
    """Wrap an HR callback to simultaneously write high-resolution frames."""
    import time

    def cb(data: Any) -> None:
        dashboard_cb(data)
        frame_logger.write_frame(int(time.time() * 1e9), data)

    return cb
