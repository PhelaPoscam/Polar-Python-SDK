"""CSV exporter for standardized packets."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ..schemas import SignalPacket


def _flatten_packet(packet: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {
        "timestamp": packet.get("timestamp"),
        "source": packet.get("source"),
        "subject_id": packet.get("subject_id"),
    }
    for key, value in (packet.get("signals") or {}).items():
        flat[f"signals.{key}"] = value
    for key, value in (packet.get("features") or {}).items():
        flat[f"features.{key}"] = value
    return flat


class CsvSink:
    """Append packets as rows in a CSV file."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, packet: SignalPacket | dict[str, Any]) -> None:
        if isinstance(packet, SignalPacket):
            data = packet.to_dict()
        else:
            data = packet

        flat = _flatten_packet(data)
        file_exists = self._path.exists()

        with self._path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(flat.keys()))
            if not file_exists:
                writer.writeheader()
            writer.writerow(flat)
