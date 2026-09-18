"""Pieces shared by the single-device and dual-device terminal dashboards.

Both CLIs parse the same recording flags, wire the same per-stream callbacks and
run the same render loop; only the panel layout and the CSV columns differ.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from collections.abc import Callable, Sequence
from typing import Any

from rich.live import Live

from .input.keyboard import NonBlockingKeyboardReader
from .metrics.rate_tracker import RateTracker
from .session.session import SessionManager
from .session.state import feed_hr, make_callback
from .storage.frame_logger import (
    make_frame_callback,
    make_hr_callback,
    make_ppi_callback,
)
from .ui.log_panel import LogPanel, log_event

LOG_TOGGLE = "__toggle_log__"

# (stream, argparse attribute, connector kwarg) for the per-stream overrides.
STREAM_SETTINGS: tuple[tuple[str, str, str], ...] = (
    ("ecg", "ecg_rate", "ecg_sample_rate"),
    ("acc", "acc_rate", "acc_sample_rate"),
    ("acc", "acc_range", "acc_range"),
    ("gyro", "gyro_rate", "gyro_sample_rate"),
    ("gyro", "gyro_range", "gyro_range"),
    ("mag", "mag_rate", "mag_sample_rate"),
    ("ppg", "ppg_rate", "ppg_sample_rate"),
)

_FRAME_WRAPPERS: dict[str, Callable] = {
    "hr": make_hr_callback,
    "ppi": make_ppi_callback,
}


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Register the flags both dashboards accept."""
    parser.add_argument(
        "--no-log", action="store_true", help="Disable CSV logging for this session."
    )
    parser.add_argument(
        "--markers",
        type=str,
        default=None,
        help="Custom hotkeys: KEY=LABEL,KEY2=LABEL2",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Custom root directory for recorded session data (default: ./data).",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Recording duration in seconds (stops automatically when reached).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["minimal", "moderate", "verbose"],
        default="moderate",
        help="Terminal log verbosity: minimal, moderate (default), verbose.",
    )
    parser.add_argument(
        "--no-sdk-mode",
        action="store_true",
        help="Disable SDK mode on the Sense: PPG falls back to 55 Hz and HR/PPI become available.",
    )
    parser.add_argument(
        "--sdk-mode",
        action="store_true",
        default=True,
        help="Explicitly enable SDK mode on the Sense (default).",
    )
    for opt in (
        "acc-rate",
        "acc-range",
        "gyro-rate",
        "gyro-range",
        "mag-rate",
        "ppg-rate",
        "ecg-rate",
    ):
        parser.add_argument(f"--{opt}", type=int, default=None, help=f"Custom {opt}")


def stream_setting_kwargs(
    args: argparse.Namespace, streams: Sequence[str]
) -> dict[str, Any]:
    """Collect the user's rate/range overrides for the streams actually enabled."""
    return {
        kwarg: getattr(args, attr)
        for stream, attr, kwarg in STREAM_SETTINGS
        if stream in streams and getattr(args, attr, None)
    }


def build_stream_callbacks(
    streams: Sequence[str],
    state: dict[str, Any],
    tracker: RateTracker,
    *,
    session_mgr: SessionManager | None = None,
    sub_device: str | None = None,
    key_prefix: str = "",
) -> dict[str, Callable[[Any], None]]:
    """One callback per stream, optionally teeing each into a raw frame log.

    ``key_prefix`` namespaces the tracker keys (``h10_acc`` vs ``sense_acc``) so a
    dual session can share one :class:`RateTracker`.
    """
    prefix = f"{key_prefix}_" if key_prefix else ""

    def _hr_cb(data: Any) -> None:
        feed_hr(data, state)

    callbacks: dict[str, Callable[[Any], None]] = {
        s: _hr_cb if s == "hr" else make_callback(state, tracker, s, key=f"{prefix}{s}")
        for s in streams
    }

    if session_mgr is not None:
        for s in streams:
            frame_logger = session_mgr.create_frame_logger(s, sub_device=sub_device)
            wrap = _FRAME_WRAPPERS.get(s, make_frame_callback)
            callbacks[s] = wrap(callbacks[s], frame_logger)

    return callbacks


async def run_dashboard(
    live: Live,
    build: Callable[[], Any],
    *,
    reader: NonBlockingKeyboardReader,
    log_panel: LogPanel,
    log_file: Any = None,
    device: str = "",
    start: float,
    duration: int | None = None,
    on_marker: Callable[[str], None] = lambda _marker: None,
    write_rows: Callable[[str], None] = lambda _marker: None,
    frame_check: Callable[[], None] = lambda: None,
) -> None:
    """Render loop: poll hotkeys, write the 1 Hz rows, refresh the panel.

    Returns when ``duration`` elapses; otherwise runs until cancelled.
    """
    last_row = start
    last_frame_log = start
    pending_markers: list[str] = []

    while True:
        for marker in reader.poll_markers():
            if marker == LOG_TOGGLE:
                log_event(
                    log_panel,
                    f"Log level: {log_panel.cycle_level()}",
                    "info",
                    device=device,
                    log_file=log_file,
                )
                continue
            pending_markers.append(marker)
            on_marker(marker)
            log_event(
                log_panel,
                f"Marker: {marker}",
                "info",
                device=device,
                log_file=log_file,
            )

        now = time.time()
        if (now - last_row) >= 1.0:
            last_row = now
            active_marker = ";".join(pending_markers) if pending_markers else ""
            pending_markers.clear()
            write_rows(active_marker)

        if log_panel.level == "verbose" and (now - last_frame_log) >= 1.0:
            last_frame_log = now
            frame_check()

        if duration and (now - start) >= duration:
            if pending_markers:
                write_rows(";".join(pending_markers))
                pending_markers.clear()
            log_event(
                log_panel,
                f"Target duration ({duration}s) reached.",
                "info",
                device=device,
                log_file=log_file,
            )
            return

        live.update(build())
        await asyncio.sleep(0.1)
