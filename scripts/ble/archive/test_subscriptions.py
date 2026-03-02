#!/usr/bin/env python3
"""Test subscribing to all notifiable characteristics"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from awe_polar.nuanic_ring.connector import NuanicConnector


def notification_handler(sender, data):
    """Handle notifications"""
    print(f"[DATA] {sender.uuid}: {data.hex()}")


async def main():
    connector = NuanicConnector()
    
    if not await connector.connect():
        return
    
    print("\n" + "=" * 80)
    print("TESTING SUBSCRIPTIONS")
    print("=" * 80 + "\n")
    
    # Find all notifiable characteristics (skip battery)
    notifiable = []
    for service in connector.client.services:
        for char in service.characteristics:
            if "notify" in char.properties and char.uuid != "00002a19-0000-1000-8000-00805f9b34fb":
                notifiable.append(char)
    
    print(f"Found {len(notifiable)} notifiable characteristics:\n")
    
    # Try subscribing to each
    for char in notifiable:
        try:
            await connector.client.start_notify(char.uuid, notification_handler)
            print(f"[OK] Subscribed to {char.uuid} (handle {char.handle:04X})")
        except Exception as e:
            print(f"[FAIL] Failed {char.uuid} (handle {char.handle:04X}): {e}")
    
    # Listen for 10 seconds
    print("\nListening for 10 seconds...")
    await asyncio.sleep(10)
    
    await connector.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
