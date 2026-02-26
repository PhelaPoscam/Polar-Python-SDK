"""Line-delimited JSON exporter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..schemas import SignalPacket


class JsonLinesSink:
    """Append packets as JSON lines to a file."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, packet: SignalPacket | dict[str, Any]) -> None:
        if isinstance(packet, SignalPacket):
            line = packet.to_json()
        else:
            line = SignalPacket(**packet).to_json()
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
