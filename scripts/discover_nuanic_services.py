import asyncio
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "src"))
from awe_polar.nuanic_ring.connector import NuanicConnector

async def main():
    """Connects to a Nuanic ring and discovers its BLE services."""
    connector = NuanicConnector()
    
    # You can specify a target address here if you know it
    # connector.target_address = "XX:XX:XX:XX:XX:XX"

    if await connector.connect():
        await asyncio.sleep(2) # Wait for connection to stabilize
        await connector.discover_services()
        # await connector.disconnect() # Keep connection alive


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[STOP] Script interrupted by user.")
