"""Low-level PMD protocol CLI: scan for Polar devices, inspect them, stream raw data."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import PolarDevice
from .constants import PmdMeasurementType
from .models import MeasurementSettings

console = Console()

STREAM_TYPES: set[str] = {"ecg", "acc", "ppi", "ppg", "gyro", "mag", "hr"}
# Streams the device configures itself; passing settings to them is an error.
UNCONFIGURABLE_STREAMS: set[str] = {"ppi", "hr"}


class Out:
    """Report progress and results as Rich text, or as newline-delimited JSON.

    Every command speaks through one of these, so the two output modes cannot
    drift apart the way parallel ``if as_json:`` branches do.
    """

    def __init__(self, as_json: bool) -> None:
        self.json = as_json

    def status(self, message: str) -> Any:
        """Spinner while a slow call runs; silent in JSON mode."""
        if self.json:
            return contextlib.nullcontext()
        return console.status(f"[bold yellow]{message}[/bold yellow]", spinner="dots")

    def emit(self, payload: dict[str, Any] | None = None, rich: Any = None) -> None:
        """Print the JSON payload or the Rich renderable, whichever mode is on."""
        if self.json:
            if payload is not None:
                print(json.dumps(payload, ensure_ascii=False))
        elif rich is not None:
            console.print(rich)

    def error(self, message: str) -> int:
        """Report a failure and return the process exit code."""
        self.emit({"error": message}, f"[bold red]{message}[/bold red]")
        return 1


def stream_callback(out: Out, label: str) -> Callable[[Any], None]:
    """Build the per-sample printer for one stream type."""

    def callback(data: Any) -> None:
        out.emit(
            {"type": label, "data": asdict(data)},
            f"[bold green]{label}:[/bold green] {data}",
        )

    return callback


def _match_device(
    devices: list[BLEDevice],
    address: str | None,
    name: str | None,
    name_contains: str | None,
) -> BLEDevice | None:
    if address:
        return next((d for d in devices if d.address == address), None)
    if name:
        return next((d for d in devices if d.name == name), None)
    if name_contains:
        needle = name_contains.lower()
        return next(
            (d for d in devices if d.name and needle in d.name.lower()),
            None,
        )
    return None


async def _find_device(
    out: Out,
    address: str | None,
    name: str | None,
    name_contains: str | None,
    timeout: float,
) -> BLEDevice | None:
    """Scan and return the one requested device, reporting why if there is none."""
    if not any([address, name, name_contains]):
        out.error("One of --address, --name, or --name-contains is required.")
        return None

    with out.status("Searching for Polar devices..."):
        devices = await BleakScanner.discover(timeout=timeout)

    device = _match_device(devices, address, name, name_contains)
    if not device:
        out.error("No matching device found.")
    return device


async def scan(timeout: float, name_contains: str, as_json: bool) -> int:
    out = Out(as_json)
    with out.status("Searching for Polar devices..."):
        devices = await BleakScanner.discover(timeout=timeout)

    needle = name_contains.lower()
    matches = [d for d in devices if d.name and needle in d.name.lower()]

    if not matches:
        out.emit(
            None, f"[bold red]No devices found matching '{name_contains}'.[/bold red]"
        )
        return 0

    table = Table(
        title="Discovered Polar Devices", show_header=True, header_style="bold magenta"
    )
    table.add_column("Name", style="bold")
    table.add_column("Address", style="cyan")
    for device in matches:
        out.emit({"name": device.name, "address": device.address})
        table.add_row(device.name, device.address)

    out.emit(None, f"[bold green]Found {len(matches)} Polar device(s).[/bold green]\n")
    out.emit(None, table)
    return 0


async def inspect_device(
    address: str | None,
    name: str | None,
    name_contains: str | None,
    timeout: float,
    as_json: bool,
) -> int:
    out = Out(as_json)
    device = await _find_device(out, address, name, name_contains, timeout)
    if not device:
        return 1

    out.emit(
        None,
        Panel(
            f"[bold green]Selected:[/bold green] [bold white]{device.name}[/bold white]\n"
            f"[bold cyan]Address:[/bold cyan] {device.address}",
            title="Inspecting",
            border_style="green",
            expand=False,
        ),
    )

    polar_device = PolarDevice(device)
    with out.status(f"Connecting to {device.name}..."):
        await polar_device.connect()

    try:
        with out.status("Fetching device features and settings..."):
            settings_by_feature: list[
                tuple[PmdMeasurementType, MeasurementSettings]
            ] = [
                (feature, await polar_device.request_stream_settings(feature))
                for feature in await polar_device.get_available_features()
            ]

        out.emit(
            {
                "name": device.name,
                "address": device.address,
                "features": [
                    {
                        "id": feature.value,
                        "name": feature.name,
                        "settings": {
                            setting.type.name.lower(): setting.values
                            for setting in settings.settings
                        },
                    }
                    for feature, settings in settings_by_feature
                ],
            }
        )

        table = Table(
            title="Available Stream Settings",
            show_header=True,
            header_style="bold magenta",
            show_lines=True,
        )
        table.add_column("Feature ID", justify="center", style="dim")
        table.add_column("Measurement Type", justify="center", style="bold")
        table.add_column("Supported Parameters", style="green")
        for feature, settings in settings_by_feature:
            params = [
                f"{s.type.name}: [{', '.join(map(str, s.values))}]"
                for s in settings.settings
            ]
            table.add_row(
                str(feature.value),
                feature.name,
                " | ".join(params) or "[dim]No configurable parameters[/dim]",
            )
        out.emit(None, table)
        return 0
    finally:
        with out.status(f"Disconnecting from {device.name}..."):
            await polar_device.disconnect()
        out.emit(None, f"[bold green]Disconnected from {device.name}.[/bold green]")


def parse_stream_spec(spec: str) -> dict[str, Any]:
    """Parse ``ecg:sample_rate=130,resolution=14`` into a stream configuration."""
    stream_type_part, separator, params_part = spec.partition(":")
    stream_type = stream_type_part.strip().lower()

    if not stream_type:
        raise ValueError("Stream type cannot be empty.")
    if stream_type not in STREAM_TYPES:
        raise ValueError(f"Unsupported stream type: {stream_type}")

    params: dict[str, int] = {}
    if separator:
        if not params_part.strip():
            raise ValueError(f"Stream '{stream_type}' has an empty parameter list.")
        if stream_type in UNCONFIGURABLE_STREAMS:
            raise ValueError(f"Stream '{stream_type}' takes no parameters.")

        for raw_param in params_part.split(","):
            param = raw_param.strip()
            if not param:
                raise ValueError(
                    f"Stream '{stream_type}' contains an empty parameter entry."
                )

            key, has_value, value = param.partition("=")
            param_name = key.strip().lower()

            if not has_value:
                raise ValueError(
                    f"Stream '{stream_type}' parameter '{param}' must use key=value format."
                )
            if not param_name:
                raise ValueError(
                    f"Stream '{stream_type}' contains a parameter with an empty name."
                )
            if param_name in params:
                raise ValueError(
                    f"Stream '{stream_type}' contains duplicate parameter '{param_name}'."
                )

            try:
                params[param_name] = int(value.strip())
            except ValueError as exc:
                raise ValueError(
                    f"Stream '{stream_type}' parameter '{param_name}' must be an integer."
                ) from exc

    return {"type": stream_type, "params": params}


async def stream_device(
    address: str | None,
    name: str | None,
    name_contains: str | None,
    timeout: float,
    duration: int,
    stream_specs: list[str] | None,
    as_json: bool,
) -> int:
    out = Out(as_json)

    if not stream_specs:
        return out.error("At least one --stream option is required.")
    try:
        stream_configs = [parse_stream_spec(spec) for spec in stream_specs]
    except ValueError as exc:
        return out.error(f"Invalid --stream: {exc}")

    device = await _find_device(out, address, name, name_contains, timeout)
    if not device:
        return 1

    out.emit(
        {"event": "device_selected", "name": device.name, "address": device.address},
        Panel(
            f"[bold green]Selected:[/bold green] [bold white]{device.name}[/bold white]\n"
            f"[bold cyan]Address:[/bold cyan] {device.address}",
            title="Streaming",
            border_style="green",
            expand=False,
        ),
    )

    polar_device = PolarDevice(device)
    with out.status(f"Connecting to {device.name}..."):
        await polar_device.connect()

    try:
        summary = Table(
            title="Final Configuration Summary", border_style="green", show_lines=True
        )
        summary.add_column("Measurement Type", justify="center", style="bold")
        summary.add_column("Selected Settings", style="cyan")
        for config in stream_configs:
            summary.add_row(
                config["type"].upper(),
                " | ".join(f"{k}: {v}" for k, v in config["params"].items())
                or "[dim]No parameters[/dim]",
            )
        out.emit(
            {"event": "connected", "name": device.name, "address": device.address},
            f"[bold green]Successfully connected to {device.name}.[/bold green]\n",
        )
        out.emit({"event": "stream_config", "streams": stream_configs}, summary)

        for config in stream_configs:
            stream_type = config["type"]
            start = getattr(polar_device, f"start_{stream_type}_stream")
            await start(stream_callback(out, stream_type.upper()), **config["params"])

        out.emit(
            {"event": "streaming_started", "duration": duration},
            (
                "\n[bold cyan]Streaming started. Press Ctrl+C to stop.[/bold cyan]\n"
                if duration == -1
                else f"\n[bold cyan]Streaming started. Running for {duration} second(s).[/bold cyan]\n"
            ),
        )
        if duration == -1:
            await asyncio.Future()
        else:
            await asyncio.sleep(duration)

        out.emit(
            {"event": "streaming_completed"},
            "\n[bold green]Streaming completed successfully.[/bold green]",
        )
        return 0
    finally:
        with out.status(f"Disconnecting from {device.name}..."):
            await polar_device.disconnect()
        out.emit(
            {"event": "disconnected", "name": device.name, "address": device.address},
            f"[bold green]Disconnected from {device.name}.[/bold green]",
        )


def _add_device_selectors(parser: argparse.ArgumentParser, verb: str) -> None:
    parser.add_argument("--address", help=f"Exact device address to {verb}")
    parser.add_argument("--name", help=f"Exact device name to {verb}")
    parser.add_argument(
        "--name-contains",
        help="Case-insensitive device name filter; uses the first match",
    )


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Scan timeout in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output newline-delimited JSON instead of rich text",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m polar_ble_sdk._pmd")
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="Scan nearby Polar devices")
    scan_parser.add_argument(
        "--name-contains",
        default="polar",
        help="Case-insensitive device name filter (default: polar)",
    )
    _add_common(scan_parser)

    inspect_parser = subparsers.add_parser(
        "inspect", help="Inspect a Polar device and list its stream settings"
    )
    _add_device_selectors(inspect_parser, "inspect")
    _add_common(inspect_parser)

    stream_parser = subparsers.add_parser(
        "stream", help="Start one or more streams on a Polar device"
    )
    _add_device_selectors(stream_parser, "stream from")
    stream_parser.add_argument(
        "--duration",
        type=int,
        default=-1,
        help="Stream duration in seconds; -1 means run until interrupted (default: -1)",
    )
    stream_parser.add_argument(
        "-s",
        "--stream",
        action="append",
        help="Stream spec like 'hr' or 'ecg:sample_rate=130,resolution=14'; repeat to start multiple streams",
    )
    _add_common(stream_parser)

    return parser


def run() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "scan":
            return asyncio.run(
                scan(
                    timeout=args.timeout,
                    name_contains=args.name_contains,
                    as_json=args.json,
                )
            )
        if args.command == "inspect":
            return asyncio.run(
                inspect_device(
                    address=args.address,
                    name=args.name,
                    name_contains=args.name_contains,
                    timeout=args.timeout,
                    as_json=args.json,
                )
            )
        if args.command == "stream":
            return asyncio.run(
                stream_device(
                    address=args.address,
                    name=args.name,
                    name_contains=args.name_contains,
                    timeout=args.timeout,
                    duration=args.duration,
                    stream_specs=args.stream,
                    as_json=args.json,
                )
            )
    except KeyboardInterrupt:
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(run())
