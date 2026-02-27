#!/usr/bin/env python3
"""
Real-time Nuanic ring data logger with stress and EDA analysis

Usage:
    python log_nuanic_session.py [--duration SECONDS]

Example:
    python log_nuanic_session.py --duration 300
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from awe_polar.nuanic_ring import NuanicDataLogger
from awe_polar.nuanic_ring.eda_analyzer import NuanicEDAAnalyzer


async def main():
    """Run the data logger"""
    
    # Parse arguments
    duration = None
    if len(sys.argv) > 1:
        if sys.argv[1] == "--duration" and len(sys.argv) > 2:
            try:
                duration = int(sys.argv[2])
                print(f"Recording for {duration} seconds...\n")
            except ValueError:
                print("Invalid duration")
                return
    
    # Create logger
    logger = NuanicDataLogger()
    eda_analyzer = NuanicEDAAnalyzer()
    
    # Start logging
    success = await logger.start_logging(duration_seconds=duration)
    
    if success:
        print("\n✓ Session complete!")
        print(f"✓ Logged {logger.row_count} readings")
        print(f"✓ File: {logger.csv_file}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
