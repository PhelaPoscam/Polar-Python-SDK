import asyncio
import argparse
from nuanic_ring.monitor import NuanicMonitor


async def main():
    parser = argparse.ArgumentParser(
        description="AWE Wrapper for Nuanic/Moodmetric BLE Monitor"
    )
    parser.add_argument(
        "--duration", type=int, default=60, help="Monitoring duration in seconds"
    )
    parser.add_argument(
        "--waveform",
        action="store_true",
        help="Launch real-time waveform visualization",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show available BLE services and characteristics",
    )
    args = parser.parse_args()

    if args.debug:
        print("[DEBUG] BLE Services using Nuanic SDK...")
        # Target the recently discovered MAC to avoid interactive prompt
        monitor = NuanicMonitor()
        monitor.connector.target_address = "58:06:09:26:D5:F6"
        if await monitor.connector.connect():
            print(f"[CONN] Connected to {monitor.connector.target_address}")
            print("[LIST] Services and Characteristics:")
            for service in monitor.connector.client.services:
                print(f"\n[Service] {service.uuid}")
                for char in service.characteristics:
                    print(f"  [Char] {char.uuid} | Props: {','.join(char.properties)}")
            await monitor.connector.disconnect()
        return

    if args.waveform:
        from nuanic_ring.waveform_viewer import run_waveform_viewer

        print(f"🚀 Launching the live waveform viewer for {args.duration} seconds...")
        await run_waveform_viewer(window_seconds=args.duration)
    else:
        print(
            f"🚀 Launching the standalone `nuanic-ring` monitor for {args.duration} seconds..."
        )
        monitor = NuanicMonitor()
        await monitor.run(duration_seconds=args.duration)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[User Cancelled] Monitor stopped gracefully.")
