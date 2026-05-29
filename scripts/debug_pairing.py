import asyncio
import time
from bleak import BleakClient


async def main():
    address = "24:AC:AC:15:19:7D"
    print(f"Connecting directly to {address} to debug pairing...")

    async with BleakClient(address) as client:
        print(f"Connected: {client.is_connected}")

        print("Calling pair()...")
        start_time = time.time()
        try:
            result = await client.pair()
            elapsed = time.time() - start_time
            print(f"pair() returned: {result}")
            print(f"Elapsed time: {elapsed:.2f} seconds")
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"pair() threw an exception: {e}")
            print(f"Elapsed time: {elapsed:.2f} seconds")


if __name__ == "__main__":
    asyncio.run(main())
