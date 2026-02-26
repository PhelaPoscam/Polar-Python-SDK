"""Dataset replay utilities for connector outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from ..schemas import SignalPacket


def iter_csv(
    path: Path | str,
    column_map: dict[str, dict[str, str]],
    source: str = "dataset",
    subject_id: str | None = None,
) -> Iterator[SignalPacket]:
    """Yield standardized packets from a CSV dataset.

    column_map example:
        {
            "signals": {"hr_bpm": "HR"},
            "features": {"rmssd": "RMSSD"}
        }
    """
    df = pd.read_csv(path)
    for _, row in df.iterrows():
        signals = {
            key: row[value]
            for key, value in (column_map.get("signals") or {}).items()
            if value in row
        }
        features = {
            key: row[value]
            for key, value in (column_map.get("features") or {}).items()
            if value in row
        }
        yield SignalPacket(
            source=source,
            subject_id=subject_id,
            signals=signals,
            features=features,
        )
