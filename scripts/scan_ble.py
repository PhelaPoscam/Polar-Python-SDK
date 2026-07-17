import asyncio

from bleak import BleakScanner


async def main():
    print("Scanning for BLE devices for 10 seconds...")
    devices = await BleakScanner.discover(timeout=10.0)
    print("\nDiscovered Devices:")
    print("=" * 60)
    for idx, d in enumerate(devices):
        name = d.name if d.name else "Unknown/Desconhecido"
        print(f"{idx + 1}. {name} [{d.address}]")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
