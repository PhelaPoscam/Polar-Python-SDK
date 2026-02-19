"""Shared data contracts for connector outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from time import time
from typing import Any


@dataclass
class SignalPacket:
    """Standardized data packet for downstream consumers."""

    timestamp: float = field(default_factory=time)
    source: str = "unknown"
    subject_id: str | None = None
    signals: dict[str, Any] = field(default_factory=dict)
    features: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "source": self.source,
            "subject_id": self.subject_id,
            "signals": dict(self.signals),
            "features": dict(self.features),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))
