"""Rich UI layout components: device panels, header strips, and footer info bars."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def device_panel(
    state: dict[str, Any],
    is_h10: bool,
    _rmssd: float | None = None,
) -> Panel:
    """Build a Rich Panel displaying live sensor metrics."""

    def _hr_style(val: int) -> str:
        if val > 90:
            return "bold red blink"
        if val > 55:
            return "bold green"
        return "red"

    hr_text = Text()
    hr_text.append(f"{state['hr']:3d}", style=_hr_style(state["hr"]))
    hr_text.append(" BPM", style="dim white")

    rr_display = [f"{rr:.0f}" for rr in list(state.get("rr_intervals", []))[-3:]]
    rr_text = Text()
    rr_text.append(f"RR: {rr_display} ms", style="bold magenta")

    metrics = Table.grid(expand=True)
    metrics.add_column(ratio=1)
    metrics.add_column(ratio=1)
    metrics.add_row(
        Panel(hr_text, title="Heart Rate", border_style="red", expand=True),
        Panel(
            rr_text,
            title="RR Intervals (last 3)",
            border_style="magenta",
            expand=True,
        ),
    )

    streams = Table(expand=True)
    streams.add_column("Stream", style="cyan")
    streams.add_column("Status", style="magenta")
    streams.add_column("Latest", style="green", ratio=2)

    streams.add_row(
        "HR",
        "Active" if state["hr"] > 0 else "Waiting...",
        f"HR={state['hr']} BPM, RR={rr_display}",
    )

    if is_h10:
        streams.add_row(
            "ECG",
            "Active" if state.get("ecg_hz", 0) > 0 else "Inactive",
            state.get("ecg_last_sample", "-"),
        )
        streams.add_row(
            "ACC",
            "Active" if state.get("acc_hz", 0) > 0 else "Inactive",
            state.get("acc_last_sample", "-"),
        )
    else:
        streams.add_row(
            "PPG",
            "Active" if state.get("ppg_hz", 0) > 0 else "Inactive",
            state.get("ppg_last_sample", "-"),
        )
        streams.add_row(
            "ACC",
            "Active" if state.get("acc_hz", 0) > 0 else "Inactive",
            state.get("acc_last_sample", "-"),
        )
        streams.add_row(
            "GYRO",
            "Active" if state.get("gyro_hz", 0) > 0 else "Inactive",
            state.get("gyro_last_sample", "-"),
        )
        streams.add_row(
            "MAG",
            "Active" if state.get("mag_hz", 0) > 0 else "Inactive",
            state.get("mag_last_sample", "-"),
        )
        streams.add_row(
            "PPI",
            "Active" if state.get("ppi_hz", 0) > 0 else "Inactive",
            state.get("ppi_last_sample", "-"),
        )

    group = Group(metrics, streams)
    border = (
        "green" if "connected" in str(state.get("status", "")).lower() else "yellow"
    )
    return Panel(
        group,
        title=f"{state.get('name', 'Device')} Dashboard",
        border_style=border,
        expand=True,
    )


def header_bar(
    device_name: str = "",
    device_addr: str = "",
    status: str = "",
) -> Text:
    """Build a slim top identity strip with connection status indicators."""
    t = Text()
    if device_name:
        t.append(device_name, style="bold cyan")
    if device_addr:
        t.append(f" ({device_addr})", style="dim cyan")
    if status:
        dot = "●" if "connected" in status.lower() else "○"
        style = "bold green" if "connected" in status.lower() else "bold yellow"
        t.append(f"  {dot} {status}", style=style)
    return t


def info_bar(
    elapsed: float,
    battery: str = "",
    csv_path: str = "",
    csv_rows: int = 0,
    marker_legend: str = "",
    log_level: str = "moderate",
) -> Panel:
    """Build a compact status footer displaying battery, elapsed time, CSV stats, and hotkeys."""
    t = Text()
    if battery and battery != "-":
        t.append(f"🔋 {battery}", style="green")
    t.append(f"  ⏱ {elapsed:.1f}s", style="bold green")
    if csv_path and csv_path != "-":
        t.append(f"  📄 {Path(csv_path).name} ({csv_rows} rows)", style="cyan")
    if marker_legend:
        t.append(f"  ⌨ {marker_legend}", style="dim yellow")
    t.append(f"  L:Log({log_level[0].upper()})", style="dim yellow")
    return Panel(t, border_style="dim white", expand=True)
