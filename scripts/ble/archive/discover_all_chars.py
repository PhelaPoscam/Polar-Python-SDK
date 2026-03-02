"""Discover all Nuanic ring BLE characteristics"""
import asyncio
from bleak import BleakClient, BleakScanner

async def discover():
    print("Scanning for Nuanic ring...")
    devices = await BleakScanner.discover(timeout=3.0)
    
    nuanic = [d for d in devices if d.name and 'Nuanic' in d.name]
    if not nuanic:
        print("Nuanic ring not found!")
        return
    
    print(f"Found: {nuanic[0].name} at {nuanic[0].address}")
    
    client = BleakClient(nuanic[0])
    await client.connect()
    await client.pair()
    
    print("\nAll BLE Services and Characteristics:")
    print("=" * 80)
    
    for service in client.services:
        print(f"\nService: {service.uuid}")
        print(f"  Description: {service.description}")
        
        for char in service.characteristics:
            props = ', '.join(char.properties)
            print(f"  └─ Characteristic: {char.uuid}")
            print(f"     Properties: {props}")
            print(f"     Handle: {char.handle}")
    
    await client.disconnect()

asyncio.run(discover())
