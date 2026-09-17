#!/usr/bin/env python3
"""Dual-device terminal dashboard for simultaneous recording of Polar H10 + Verity Sense."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from polar_ble_sdk.dual_cli import _entrypoint  # noqa: E402

if __name__ == "__main__":
    _entrypoint()
