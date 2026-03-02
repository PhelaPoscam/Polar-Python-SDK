#!/usr/bin/env python3
"""Try sending commands to enable streaming"""
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
    
    print("\nTrying to enable streaming via write commands...")
    
    # Try writing to known write-only characteristics
    write_characteristics = [
        ("2175c13f-60e4-4de5-80af-0d06f1b54880", b"\x01"),  # [001F]
        ("741f0d15-cc3d-4715-a9fb-a5a6bccebc50", b"\x01"),  # [0023]
        ("da2e7828-fbce-4e01-ae9e-261174997c48", b"\x01"),  # [0033]
    ]
    
    for uuid, data in write_characteristics:
        try:
            await connector.client.write_gatt_char(uuid, data)
            print(f"[OK] Wrote to {uuid}: {data.hex()}")
        except Exception as e:
            print(f"[FAIL] Write to {uuid}: {e}")
    
    print("\nNow trying subscriptions...")
    
    def notification_handler(sender, data):
        print(f"[DATA] {sender.uuid[:8]}...: {data[:20].hex()}...")
    
    # Try stress characteristic
    try:
        stress_uuid = "468f2717-6a7d-46f9-9eb7-f92aab208bae"
        await connector.client.start_notify(stress_uuid, notification_handler)
        print(f"[OK] Subscribed to stress/EDA!")
        
        print("\nListening for 10 seconds...")
        await asyncio.sleep(10)
    except Exception as e:
        print(f"[FAIL] Stress subscription: {e}")
    
    await connector.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
