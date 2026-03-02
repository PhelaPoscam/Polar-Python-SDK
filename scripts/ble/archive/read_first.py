#!/usr/bin/env python3
"""Try reading first, then subscribing"""
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
    
    print(f"\nConnection status: {connector.client.is_connected}")
    
    if not connector.client.is_connected:
        print("[FAIL] Lost connection immediately after pairing!")
        return
    
    print("\nTrying to READ characteristics (not subscribe)...")
    
    # Discover ALL readable characteristics from the connected ring
    readable_chars = []
    for service in connector.client.services:
        for char in service.characteristics:
            if "read" in char.properties:
                readable_chars.append((char.uuid, char.uuid[:8] if len(str(char.uuid)) > 8 else str(char.uuid)))
    
    print(f"Found {len(readable_chars)} readable characteristics\n")
    
    for uuid, short_name in readable_chars:
        if not connector.client.is_connected:
            print(f"[FAIL] Connection lost before {short_name}")
            break
        try:
            data = await connector.client.read_gatt_char(uuid)
            print(f"[OK] {short_name}...: {data.hex()[:40]}{'...' if len(data.hex()) > 40 else ''}")
        except Exception as e:
            print(f"[FAIL] {short_name}...: {str(e)[:50]}")
    
    await connector.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
