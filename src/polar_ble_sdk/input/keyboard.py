"""Cross-platform non-blocking keyboard input and experiment marker ingestion."""

from __future__ import annotations

import sys
import time
from typing import Any


class NonBlockingKeyboardReader:
    """Non-blocking keyboard reader supporting experiment hotkeys and arbitrary text markers."""

    def __init__(self, hotkeys: dict[str, str] | None = None) -> None:
        self._buffer = ""
        self._win_msvcrt: Any = None
        self._last_space_ts = 0.0
        base_hotkeys = hotkeys or {
            "SPACE": "marker",
            "S": "stimulus_on",
            "B": "baseline_start",
            "R": "rest_start",
        }
        self._hotkeys = {key.upper(): value for key, value in base_hotkeys.items()}
        if sys.platform == "win32":
            import msvcrt

            self._win_msvcrt = msvcrt

    def poll_markers(self) -> list[str]:
        """Poll non-blocking keyboard input and return triggered markers."""
        markers: list[str] = []
        if self._win_msvcrt is not None:
            while self._win_msvcrt.kbhit():
                ch = self._win_msvcrt.getwch()
                if ch == " ":
                    now = time.monotonic()
                    if (now - self._last_space_ts) >= 0.2:
                        marker = self._hotkeys.get("SPACE")
                        if marker:
                            markers.append(marker)
                        self._last_space_ts = now
                    continue
                if len(ch) == 1:
                    ch_upper = ch.upper()
                    marker = self._hotkeys.get(ch_upper)
                    if marker:
                        markers.append(marker)
                        continue
                    if ch in ("\r", "\n"):
                        line = self._buffer.strip()
                        self._buffer = ""
                        if line:
                            markers.append(line)
                    else:
                        self._buffer += ch
        else:
            import select

            if select.select([sys.stdin], [], [], 0.0)[0]:
                line = sys.stdin.readline().strip()
                if line:
                    line_upper = line.upper()
                    if line_upper in self._hotkeys:
                        markers.append(self._hotkeys[line_upper])
                    else:
                        markers.append(line)
        return markers


def parse_marker_specs(specs_str: str | None) -> dict[str, str]:
    """Parse comma-separated KEY=LABEL hotkey definitions into a dictionary."""
    hotkeys = {
        "SPACE": "marker",
        "S": "stimulus_on",
        "B": "baseline_start",
        "R": "rest_start",
    }
    if not specs_str:
        return hotkeys
    parts = [p.strip() for p in specs_str.split(",") if p.strip()]
    for part in parts:
        if "=" in part:
            k, v = part.split("=", 1)
            k, v = k.strip().upper(), v.strip()
            if k == "L":
                raise ValueError("'L' is reserved for the log-level toggle.")
            if k and v:
                hotkeys[k] = v
    return hotkeys


def format_marker_legend(hotkeys: dict[str, str]) -> str:
    """Format hotkey mapping into a readable terminal footer string."""
    return " | ".join(f"{k}={hotkeys[k]}" for k in sorted(hotkeys))
