"""1 Hz summary CSV logging utility for multi-parameter session data."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CsvLogger:
    """Manages writing synchronized summary rows to a CSV file."""

    def __init__(self, path: Path | str | None, columns: list[str]) -> None:
        self._path = Path(path) if path else None
        self._columns = columns
        self.rows_written = 0

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def path_str(self) -> str:
        return str(self._path) if self._path else "-"

    def write_header(self) -> None:
        """Create parent directory and write CSV column header."""
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(self._columns)

    def write_row(self, values: list[Any]) -> None:
        """Append a single row of values to the CSV file."""
        if not self._path:
            return
        try:
            with self._path.open("a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(values)
            self.rows_written += 1
        except OSError as e:
            logger.warning("CSV write failed to %s: %s", self._path, e)
