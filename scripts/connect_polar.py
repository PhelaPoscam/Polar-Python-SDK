#!/usr/bin/env python3
"""Run basic single-device Polar streaming connection example."""

import runpy
from pathlib import Path

if __name__ == "__main__":
    example_path = Path(__file__).resolve().parents[1] / "examples" / "connect_polar.py"
    runpy.run_path(str(example_path), run_name="__main__")
