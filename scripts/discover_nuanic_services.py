#!/usr/bin/env python3
"""Discover Nuanic ring BLE services - Use for debugging."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from awe_polar.nuanic_ring.connector import NuanicConnector


async def main():
    """Connects to a Nuanic ring and discovers its BLE services."""
    connector = NuanicConnector()
    
    print("\n" + "="*60)
    print("NUANIC RING SERVICE DISCOVERY")
    print("="*60)
    
    if await connector.connect():
        print("\n[OK] Connected, discovering services...\n")
        await asyncio.sleep(1)  # Stabilize connection
        await connector.discover_services()
        await connector.disconnect()
    else:
        print("\n[FAIL] Could not connect to ring")
        return 1
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[STOP] Interrupted by user")
        sys.exit(1)

