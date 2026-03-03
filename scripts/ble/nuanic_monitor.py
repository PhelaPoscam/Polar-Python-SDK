"""CLI entrypoint for Nuanic monitor (IMU + Stress + EDA)."""
import argparse
import asyncio

from src.awe_polar.nuanic_ring.connector import NuanicConnector
from src.awe_polar.nuanic_ring.monitor import NuanicMonitor


async def main():
    parser = argparse.ArgumentParser(
        description="Monolithic Nuanic monitor (IMU + Stress + EDA)"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Duration in seconds (omit for indefinite)",
    )
    parser.add_argument(
        "--log-dir",
        default="data/nuanic_logs",
        help="Directory to save CSV files",
    )
    parser.add_argument(
        "--imu-refresh",
        type=int,
        default=5,
        help="Refresh display every N IMU packets",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not clear terminal on refresh",
    )
    parser.add_argument(
        "--ring-addr",
        default=None,
        help="BLE address of ring to connect to (e.g., AA:BB:CC:DD:EE:FF)",
    )
    parser.add_argument(
        "--list-rings",
        action="store_true",
        help="List all available Nuanic rings and exit",
    )
    parser.add_argument(
        "--docked",
        action="store_true",
        help="Auto-connect to the docked ring (if only one found)",
    )
    args = parser.parse_args()

    # Handle --list-rings: scan and show available devices
    if args.list_rings:
        try:
            connector = NuanicConnector()
            rings = await connector.list_available_rings()
            
            if not rings:
                print("\n❌ No Nuanic rings found")
                return
            
            print(f"\n✅ Found {len(rings)} Nuanic ring(s):\n")
            for i, ring in enumerate(rings, 1):
                print(f"  {i}. {ring['name']:20} | Address: {ring['address']}")
            print()
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n[STOP] Scan cancelled")
        return

    # Handle ring selection when --ring-addr is not provided.
    ring_address = args.ring_addr
    if not ring_address:
        try:
            connector = NuanicConnector()
            rings = await connector.list_available_rings()
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n[STOP] Scan cancelled")
            return
        
        # Handle --docked mode: auto-connect if exactly 1 ring found
        if args.docked:
            if len(rings) == 1:
                ring_address = rings[0]["address"]
                print(
                    f"🔌 Docked mode: Using {rings[0]['name']} "
                    f"({rings[0]['address']})\n"
                )
            elif len(rings) == 0:
                print(
                    "\n❌ No Nuanic rings found "
                    "(docked mode expected to find exactly 1)"
                )
                return
            else:
                print(
                    f"\n⚠️  Docked mode found {len(rings)} rings, "
                    "but expected 1:"
                )
                for i, ring in enumerate(rings, 1):
                    print(f"  {i}. {ring['name']:20} | {ring['address']}")
                print(
                    "\nPlease remove unused rings or use --ring-addr "
                    "to specify\n"
                )
                return
        elif len(rings) > 1:
            print(f"\n⚠️  Found {len(rings)} Nuanic rings:\n")
            for i, ring in enumerate(rings, 1):
                print(f"  {i}. {ring['name']:20} | {ring['address']}")
            
            while True:
                try:
                    choice = input(
                        "\nSelect ring (1-{}) or press Enter for first ring: ".format(
                            len(rings)
                        )
                    )
                    if not choice:
                        ring_address = rings[0]["address"]
                        print(f"Using: {rings[0]['name']} ({rings[0]['address']})\n")
                        break
                    idx = int(choice) - 1
                    if 0 <= idx < len(rings):
                        ring_address = rings[idx]["address"]
                        print(f"Using: {rings[idx]['name']} ({rings[idx]['address']})\n")
                        break
                    print("Invalid selection")
                except (ValueError, KeyboardInterrupt):
                    print("Invalid input")

    try:
        monitor = NuanicMonitor(
            log_dir=args.log_dir,
            imu_refresh_packets=args.imu_refresh,
            clear_console=not args.no_clear,
            ring_address=ring_address,
        )
        await monitor.run(duration_seconds=args.duration)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[STOP] Monitor stopped")


if __name__ == "__main__":
    asyncio.run(main())
