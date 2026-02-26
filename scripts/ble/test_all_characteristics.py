"""
Test all notification characteristics on the Nuanic ring
to find which one is actually sending data.
"""

import asyncio
from bleak import BleakScanner, BleakClient
from datetime import datetime


async def test_all_notifications():
    """Scan, connect, and listen on all notify-capable characteristics."""
    
    print("\n[TEST] Scanning for Nuanic ring...")
    devices = await BleakScanner.discover(timeout=5.0)
    
    ring = None
    for device in devices:
        if device.name and ("LHB" in device.name or "Nuanic" in device.name):
            ring = device
            break
    
    if not ring:
        print("✗ Ring not found")
        return
    
    print(f"✓ Found: {ring.name} ({ring.address})\n")
    print("[TEST] Connecting and discovering all notify characteristics...\n")
    
    try:
        async with BleakClient(ring.address, timeout=20.0) as client:
            print("✓ Connected!\n")
            
            # Collect all notify characteristics
            notify_chars = []
            for service in client.services:
                for char in service.characteristics:
                    if "notify" in char.properties:
                        notify_chars.append((char.uuid, char.description or "Unknown"))
            
            print(f"Found {len(notify_chars)} notify-capable characteristics:\n")
            for uuid, desc in notify_chars:
                print(f"  • {desc}")
                print(f"    UUID: {uuid}\n")
            
            if not notify_chars:
                print("✗ No notify characteristics found")
                return
            
            # Create callback handlers for each
            call_counts = {}
            
            def make_callback(uuid):
                call_counts[uuid] = 0
                def callback(sender, data):
                    call_counts[uuid] += 1
                    count = call_counts[uuid]
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    print(f"[{timestamp}] Data from {uuid[:8]}...")
                    print(f"  Hex: {data.hex()}")
                    print(f"  Bytes: {list(data)}")
                    print()
                return callback
            
            # Subscribe to all
            print("[TEST] Subscribing to all notify characteristics...")
            for uuid, desc in notify_chars:
                try:
                    await client.start_notify(uuid, make_callback(uuid))
                    print(f"  ✓ {desc}")
                except Exception as e:
                    print(f"  ✗ {desc}: {e}")
            
            print("\n[TEST] Listening for 30 seconds...\n")
            print("=" * 60)
            
            try:
                await asyncio.sleep(30)
            except KeyboardInterrupt:
                pass
            
            print("=" * 60)
            print("\n[TEST] Summary:")
            for uuid, desc in notify_chars:
                count = call_counts.get(uuid, 0)
                print(f"  {desc}: {count} notifications")
            
            # Unsubscribe all
            for uuid, _ in notify_chars:
                try:
                    await client.stop_notify(uuid)
                except:
                    pass
    
    except Exception as e:
        print(f"✗ Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_all_notifications())
