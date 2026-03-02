#!/usr/bin/env python3
"""
Scan for all available Nuanic rings
"""
import asyncio
from bleak import BleakScanner

async def scan_rings():
    print("=" * 80)
    print("🔍 SCANNING FOR NUANIC RINGS")
    print("=" * 80)
    print()
    
    devices = await BleakScanner.discover(timeout=10.0)
    
    nuanic_devices = [d for d in devices if d.name and 'nuanic' in d.name.lower()]
    
    print(f"Total devices found: {len(devices)}")
    print(f"Nuanic devices found: {len(nuanic_devices)}")
    print()
    
    if nuanic_devices:
        print("=" * 80)
        print("NUANIC RINGS DETECTED:")
        print("=" * 80)
        for i, device in enumerate(nuanic_devices, 1):
            print()
            print(f"Ring #{i}")
            print(f"  Name: {device.name}")
            print(f"  MAC Address: {device.address}")
            print(f"  Details: {device.details if hasattr(device, 'details') else 'N/A'}")
    else:
        print("⚠️  No Nuanic rings detected")
        print()
        print("All detected devices:")
        for device in devices:
            name = device.name if device.name else "(unnamed)"
            print(f"  • {name} ({device.address})")

if __name__ == "__main__":
    asyncio.run(scan_rings())
