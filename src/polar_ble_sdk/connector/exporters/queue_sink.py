"""Queue sink for in-memory streaming."""

from __future__ import annotations

import queue
from typing import Any

from ..schemas import SignalPacket


class QueueSink:
    """Push packets into a Queue for live consumers."""

    def __init__(self, target: queue.Queue) -> None:
        self._queue = target

    def send(self, packet: SignalPacket | dict[str, Any]) -> None:
        if isinstance(packet, SignalPacket):
            payload = packet.to_dict()
        else:
            payload = packet
        self._queue.put(payload)
