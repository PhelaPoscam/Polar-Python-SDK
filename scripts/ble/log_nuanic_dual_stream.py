"""Compatibility entrypoint for the monolithic Nuanic monitor."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from nuanic_monitor import main


if __name__ == "__main__":
    asyncio.run(main())
