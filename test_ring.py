import asyncio
from nuanic_ring.monitor import NuanicMonitor

async def main():
    print("🚀 Starting Ring Monitor from the installed library...")
    # Initialize the monitor
    monitor = NuanicMonitor()
    
    if await monitor.start_monitoring():
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
