#!/usr/bin/env python3
"""
Check Nuanic ring status and connectivity
"""
import asyncio
from bleak import BleakScanner, BleakClient


async def check_nuanic_ring():
    """Check if Nuanic ring is discoverable"""
    print("\n" + "="*60)
    print("NUANIC RING STATUS CHECK")
    print("="*60 + "\n")
    
    # Step 1: BLE Scan
    print("[STEP 1] Scanning for BLE devices...")
    devices = await BleakScanner.discover(timeout=5.0)
    print(f"  Found {len(devices)} device(s)")
    
    nuanic_device = None
    for device in devices:
        if device.name and "nuanic" in device.name.lower():
            nuanic_device = device
            print(f"  ✓ NUANIC RING FOUND: {device.name}")
            break
    
    if not nuanic_device:
        print("  ✗ Nuanic ring NOT found\n")
        print("[DIAGNOSIS]")
        print("  The ring is not broadcasting. Possible causes:")
        print("  1. Ring is powered off or in dock sleep mode")
        print("  2. Ring battery is dead")
        print("  3. Ring is paired to another device")
        print("  4. Ring is in pairing mode but not advertising as 'Nuanic'\n")
        print("[ACTIONS TO TRY]")
        print("  1. Remove ring from dock")
        print("  2. Wait 3-5 seconds for it to activate")
        print("  3. Put ring on your finger for it to activate sensors")
        print("  4. Re-run this script to verify broadcast\n")
        return False
    
    # Step 2: Connect
    print(f"\n[STEP 2] Attempting connection to {nuanic_device.name}...")
    try:
        async with BleakClient(nuanic_device.address, timeout=10.0) as client:
            print(f"  ✓ Connected to {nuanic_device.address}")
            
            # List services
            services = await client.get_services()
            print(f"  ✓ Found {len(services.services)} GATT services")
            
            # Check for Nuanic service (generic health device)
            found_health_svc = False
            for service in services.services:
                if "180d" in str(service.uuid):  # Health Device service
                    found_health_svc = True
                    print(f"  ✓ Health Device Service found")
                    break
            
            if not found_health_svc:
                print("  ⚠ Health Device Service not found")
            
            # Check battery
            try:
                battery_char = "00002a19-0000-1000-8000-00805f9b34fb"
                battery = await client.read_gatt_char(battery_char)
                battery_pct = battery[0] if battery else "Unknown"
                print(f"  ✓ Battery: {battery_pct}%")
            except Exception as e:
                print(f"  ⚠ Could not read battery: {e}")
            
            print("\n" + "="*60)
            print("✓ RING IS CONNECTED AND RESPONSIVE")
            print("="*60 + "\n")
            return True
            
    except asyncio.TimeoutError:
        print(f"  ✗ Connection timeout")
        print("  Ring found but not responding. Try:")
        print("  1. Check ring battery")
        print("  2. Restart the ring (remove from dock, wait 10s, return)")
        print("  3. Check Bluetooth is enabled on this device\n")
        return False
    except Exception as e:
        print(f"  ✗ Connection failed: {e}\n")
        return False


if __name__ == "__main__":
    result = asyncio.run(check_nuanic_ring())
    exit(0 if result else 1)
