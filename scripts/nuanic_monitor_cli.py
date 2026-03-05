#!/usr/bin/env python3
"""Nuanic Ring Monitor CLI - Real-time monitoring of IMU, Stress, and EDA data."""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from awe_polar.nuanic_ring.connector import NuanicConnector
from awe_polar.nuanic_ring.monitor import NuanicMonitor


async def main():
    parser = argparse.ArgumentParser(
        description="Real-time Nuanic ring monitor (IMU + Stress + EDA)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Scan and select from available rings
  %(prog)s --duration 60                # Monitor for 60 seconds
  %(prog)s --list-rings                 # List all available rings
  %(prog)s --ring-addr 58:A3:D0:95:DF:2D --duration 30
        """
    )
    
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Duration in seconds (default: unlimited, Ctrl+C to stop)",
    )
    parser.add_argument(
        "--log-dir",
        default="data/nuanic_logs",
        help="Directory to save CSV logs (default: data/nuanic_logs)",
    )
    parser.add_argument(
        "--imu-refresh",
        type=int,
        default=5,
        help="Refresh display every N IMU packets (default: 5)",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Don't clear terminal on refresh",
    )
    parser.add_argument(
        "--ring-addr",
        default=None,
        help="BLE address of ring (e.g., 58:A3:D0:95:DF:2D). If not provided, will prompt.",
    )
    parser.add_argument(
        "--list-rings",
        action="store_true",
        help="List available rings and exit",
    )
    
    args = parser.parse_args()
    
    # Handle --list-rings
    if args.list_rings:
        try:
            connector = NuanicConnector()
            rings = await connector.list_available_rings()
            
            if not rings:
                print("\n[FAIL] No Nuanic rings found\n")
                return
            
            print(f"\n✓ Found {len(rings)} Nuanic ring(s):\n")
            for i, ring in enumerate(rings, 1):
                print(f"  {i}. {ring['name']:20} | {ring['address']}")
            print()
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n[STOP] Scan cancelled\n")
        return
    
    # Create and run monitor
    try:
        monitor = NuanicMonitor(
            log_dir=args.log_dir,
            imu_refresh_packets=args.imu_refresh,
            clear_console=not args.no_clear,
        )
        # If ring address is provided, pin to it. Otherwise connector will prompt at connect time.
        if args.ring_addr:
            monitor.connector.target_address = args.ring_addr
        
        print(
            f"\n[MONITOR] Starting with ring: {args.ring_addr if args.ring_addr else 'interactive selection'}"
        )
        print(f"[MONITOR] Duration: {args.duration if args.duration else 'unlimited'} seconds")
        print("[MONITOR] Logs saved to:", args.log_dir)
        
        await monitor.run(duration_seconds=args.duration)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[STOP] Monitor stopped")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
