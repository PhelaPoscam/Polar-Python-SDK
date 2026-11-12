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
        """Poll non-blocking keyboard input and return triggered markers.

        Windows: hotkeys fire on the key press; free text is typed as
        ``/text`` + Enter (Esc cancels it). Other keys are ignored, so a stray
        key can never hold back the hotkeys that follow it.
        """
        markers: list[str] = []
        if self._win_msvcrt is not None:
            while self._win_msvcrt.kbhit():
                ch = self._win_msvcrt.getwch()
                if ch in ("\x00", "\xe0"):
                    if self._win_msvcrt.kbhit():
                        self._win_msvcrt.getwch()
                    continue

                if self._buffer:  # typing "/text"
                    if ch == "\x08":
                        self._buffer = self._buffer[:-1]
                    elif ch == "\x1b":
                        self._buffer = ""
                    elif ch in ("\r", "\n"):
                        text = self._buffer[1:].strip()
                        self._buffer = ""
                        if text:
                            markers.append(text)
                    else:
                        self._buffer += ch
                    continue

                if ch == "/":
                    self._buffer = ch
                elif ch == " ":
                    now = time.monotonic()
                    if (now - self._last_space_ts) >= 0.2:
                        marker = self._hotkeys.get("SPACE")
                        if marker:
                            markers.append(marker)
                        self._last_space_ts = now
                else:
                    marker = self._hotkeys.get(ch.upper())
                    if marker:
                        markers.append(marker)
        else:
            import select

            if select.select([sys.stdin], [], [], 0.0)[0]:
                # Line-buffered: a bare Enter stands in for SPACE.
                raw = sys.stdin.readline()
                line = raw.strip()
                if not raw:
                    pass  # EOF (stdin closed): stays readable, never a marker
                elif not line:
                    if self._hotkeys.get("SPACE"):
                        markers.append(self._hotkeys["SPACE"])
                elif line.startswith("/"):
                    if line[1:].strip():
                        markers.append(line[1:].strip())
                else:
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
