#!/usr/bin/env python3
"""Quick characteristic discovery"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from awe_polar.nuanic_ring.connector import NuanicConnector


async def main():
    connector = NuanicConnector()
    
    if not await connector.connect():
        return
    
    print("\n" + "=" * 80)
    print("AVAILABLE CHARACTERISTICS")
    print("=" * 80)
    
    for service in connector.client.services:
        print(f"\nService: {service.uuid}")
        for char in service.characteristics:
            props = ", ".join(char.properties)
            print(f"  [{char.handle:04X}] {char.uuid}")
            print(f"         Properties: {props}")
    
    await connector.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
