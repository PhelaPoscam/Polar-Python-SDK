import asyncio
import argparse
from nuanic_ring.monitor import NuanicMonitor

async def main():
    parser = argparse.ArgumentParser(description="AWE Wrapper for Nuanic/Moodmetric BLE Monitor")
    parser.add_argument("--duration", type=int, default=60, help="Monitoring duration in seconds")
    parser.add_argument("--waveform", action="store_true", help="Launch real-time waveform visualization")
    args = parser.parse_args()

    if args.waveform:
        from nuanic_ring.waveform_viewer import run_waveform_viewer
        print(f"🚀 Launching the live waveform viewer for {args.duration} seconds...")
        await run_waveform_viewer(window_seconds=args.duration)
    else:
        print(f"🚀 Launching the standalone `nuanic-ring` monitor for {args.duration} seconds...")
        monitor = NuanicMonitor()
        await monitor.run(duration_seconds=args.duration)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[User Cancelled] Monitor stopped gracefully.")
