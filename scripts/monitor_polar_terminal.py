from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add src/ directory to sys.path to run locally during development
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

from polar_ble_sdk.cli import main  # noqa: E402

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
