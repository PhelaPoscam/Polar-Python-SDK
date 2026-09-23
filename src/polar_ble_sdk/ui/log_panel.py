"""Rolling event log panel and severity-styled logging."""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

SEVERITY_ICONS: dict[str, str] = {
    "info": "·",
    "success": "●",
    "warning": "▲",
    "error": "✖",
}

SEVERITY_STYLES: dict[str, str] = {
    "info": "dim white",
    "success": "green",
    "warning": "yellow",
    "error": "bold red",
}


def log_event(
    log_panel: LogPanel,
    msg: str,
    severity: str = "info",
    *,
    device: str = "",
    log_file: Any = None,
) -> None:
    """Format a log line and push it to the LogPanel and optional disk log file."""
    ts = time.strftime("%H:%M:%S")
    icon = SEVERITY_ICONS.get(severity, "·")
    prefix = f"[{device}] " if device else ""
    styled = Text.assemble(
        (f"{ts} ", "dim"),
        (f"{icon} ", SEVERITY_STYLES.get(severity, "dim white")),
        (f"{prefix}{msg}", SEVERITY_STYLES.get(severity, "dim white")),
    )
    log_panel.push(styled)
    if log_file:
        try:
            log_file.write(f"{ts} [{severity.upper()}] {prefix}{msg}\n")
            log_file.flush()
        except OSError:
            pass


class LogPanel:
    """Rolling tail of styled log lines with runtime severity filtering."""

    def __init__(self, max_lines: int = 200) -> None:
        self._lines: deque[Text] = deque(maxlen=max_lines)
        self._level: str = "moderate"

    @property
    def level(self) -> str:
        return self._level

    def set_level(self, level: str) -> None:
        self._level = level

    def cycle_level(self) -> str:
        """Toggle between moderate and verbose. Returns the new level."""
        self._level = "verbose" if self._level == "moderate" else "moderate"
        return self._level

    def push(self, styled_line: Text) -> None:
        self._lines.append(styled_line)

    def _visible(self) -> list[Text]:
        if self._level == "minimal":
            return [ln for ln in self._lines if not ln.plain.startswith("· ")]
        return list(self._lines)

    def render(self, height: int | None = None) -> Panel:
        visible = self._visible()
        if height is not None:
            visible = visible[-height:] if len(visible) > height else visible
        if not visible:
            visible = [Text("  waiting for events...", style="dim")]
        return Panel(
            Group(*visible),
            title="Log",
            border_style="dim white",
            expand=True,
        )
