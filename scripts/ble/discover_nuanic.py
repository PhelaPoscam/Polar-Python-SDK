"""
GATT Service Discovery for Nuanic Ring

Connects to the ring and maps all available services and characteristics.
"""

import asyncio
from bleak import BleakScanner, BleakClient


async def discover_nuanic():
    """Scan for Nuanic ring and discover all GATT services."""
    
    print("\n[SCAN] Searching for Nuanic ring...")
    print("[SCAN] Scanning for 5 seconds...\n")
    
    try:
        # First, find the device
        devices = await BleakScanner.discover(timeout=5.0)
        
        nuanic_device = None
        for device in devices:
            # Nuanic rings typically appear as "LHB-xxxx" or "Nuanic"
            if device.name and ("Nuanic" in device.name or "LHB" in device.name):
                nuanic_device = device
                print(f"✓ Found: {device.name} ({device.address})\n")
                break
        
        if not nuanic_device:
            print("✗ Nuanic ring not found")
            print("  - Ensure ring is powered on")
            print("  - Check if it's within Bluetooth range")
            print("  - Ensure it's not paired with another device")
            return
        
        # Connect and discover services
        print(f"[DISCOVERY] Connecting to {nuanic_device.name}...")
        
        async with BleakClient(nuanic_device.address, timeout=10.0) as client:
            print("[DISCOVERY] ✓ Connected!\n")
            print("=" * 80)
            print("GATT ARCHITECTURE MAPPING")
            print("=" * 80 + "\n")
            
            services = client.services
            print(f"Found {len(services)} Service(s):\n")
            
            service_count = 0
            char_count = 0
            notify_count = 0
            
            for service in services:
                service_count += 1
                print(f"┌─ Service #{service_count}")
                print(f"│  Description: {service.description if service.description else 'Unknown'}")
                print(f"│  UUID:        {service.uuid}")
                print(f"│  Characteristics: {len(service.characteristics)}\n")
                
                for char in service.characteristics:
                    char_count += 1
                    props = ", ".join(char.properties)
                    supports_notify = "notify" in char.properties
                    
                    if supports_notify:
                        notify_count += 1
                    
                    notify_marker = "→ NOTIFY ✓" if supports_notify else ""
                    
                    print(f"│  └─ Char #{char_count}")
                    print(f"│     Description: {char.description if char.description else 'Unknown'}")
                    print(f"│     UUID:        {char.uuid}")
                    print(f"│     Properties:  {props}")
                    
                    if supports_notify:
                        print(f"│     {notify_marker}")
                    
                    print()
            
            print("=" * 80)
            print(f"Summary: {service_count} services, {char_count} characteristics, {notify_count} support notifications")
            print("=" * 80 + "\n")
            
            print("📋 RECOMMENDED NEXT STEPS:")
            print("   1. Find a characteristic with 'notify' property")
            print("   2. Copy its UUID (e.g., 00002a37-0000-1000-8000-00805f9b34fb)")
            print("   3. Update TARGET_CHARACTERISTIC_UUID in ble_ring_streamer.py")
            print("   4. Run: & \".venv/Scripts/python.exe\" scripts/ble_ring_streamer.py\n")
    
    except asyncio.TimeoutError:
        print("✗ Connection timeout (10 seconds)")
        print("  - Ring may be too far away")
        print("  - Try moving closer to the device")
    except Exception as e:
        print(f"✗ Error: {e}")


if __name__ == "__main__":
    asyncio.run(discover_nuanic())
