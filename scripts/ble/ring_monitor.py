#!/usr/bin/env python3
"""
Unified Nuanic Ring Monitoring CLI
Single entry point for all ring monitoring tasks
"""
import asyncio
import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from ble_utils import RingMonitor, MultiRingMonitor, RingCharacteristics, scan_for_rings


async def cmd_monitor(args):
    """Monitor one or more rings"""
    
    # Determine which rings to monitor
    if args.auto_all:
        print("🔄 Auto-detecting all available rings...")
        rings = await scan_for_rings(timeout=30)
        if not rings:
            print("❌ No rings found")
            return False
        args.macs = rings
    elif args.macs:
        pass  # Use provided MACs
    elif args.mac:
        args.macs = [args.mac]
    else:
        print("❌ No ring(s) specified. Use --mac, --macs, or --auto-all")
        return False
    
    # Monitor single ring
    if len(args.macs) == 1:
        monitor = RingMonitor(args.macs[0], args.duration, args.log_dir, args.verbose)
        
        if not await monitor.find_ring():
            return False
        
        return await monitor.start_monitoring()
    
    # Monitor multiple rings
    else:
        print(f"🔗 Monitoring {len(args.macs)} ring(s) concurrently")
        
        monitor = MultiRingMonitor(args.macs, args.duration, args.log_dir, args.verbose)
        
        if not await monitor.find_all_rings():
            return False
        
        await monitor.start_monitoring()
        return True


async def cmd_discover(args):
    """Discover characteristics on a ring"""
    
    monitor = RingMonitor(args.mac, log_dir=args.log_dir, verbose=args.verbose)
    
    if not await monitor.find_ring():
        return False
    
    print("\n" + "=" * 80)
    print("DISCOVERING CHARACTERISTICS")
    print("=" * 80 + "\n")
    
    discovered = await monitor.discover_characteristics()
    
    if discovered:
        print(f"\n✅ Found {len(discovered)} known characteristic(s):")
        for char_uuid, char_type in discovered.items():
            print(f"  • {char_uuid}: {char_type}")
    else:
        print("⚠️  No known characteristics found")
    
    print("\n" + "=" * 80)
    return True


async def cmd_scan(args):
    """Scan for available rings"""
    
    print("=" * 80)
    print("🔍 SCANNING FOR NUANIC RINGS")
    print("=" * 80 + "\n")
    
    rings = await scan_for_rings(timeout=args.timeout)
    
    if rings:
        print(f"\n✅ Found {len(rings)} ring(s):")
        for i, mac in enumerate(rings, 1):
            print(f"  Ring #{i}: {mac}")
        print("\n💡 To monitor a ring:")
        print(f"  python ring_monitor.py --mac {rings[0]} --duration 60")
    else:
        print("\n❌ No Nuanic rings found")
    
    print("\n" + "=" * 80)
    return bool(rings)


def main():
    parser = argparse.ArgumentParser(
        description="Nuanic Ring Monitoring - Unified CLI for all ring operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Monitor a single ring
  python ring_monitor.py --mac 69:9A:5D:F8:00:C0 --duration 60
  
  # Monitor two rings concurrently
  python ring_monitor.py --macs 69:9A:5D:F8:00:C0 71:12:2B:3B:9C:4E
  
  # Auto-detect and monitor all available rings
  python ring_monitor.py --auto-all --duration 120
  
  # Discover characteristics on a ring
  python ring_monitor.py --discover 71:12:2B:3B:9C:4E
  
  # Scan for available rings
  python ring_monitor.py --scan
        """
    )
    
    # Global options
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug output"
    )
    parser.add_argument(
        "--log-dir",
        default="data/logs",
        help="Directory for log files (default: data/logs)"
    )
    
    # Subcommands / modes
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # MONITOR command (default)
    monitor_parser = subparsers.add_parser("monitor", help="Monitor ring(s) for data")
    monitor_parser.set_defaults(func=cmd_monitor)
    monitor_parser.add_argument(
        "--mac",
        help="MAC address of single ring to monitor"
    )
    monitor_parser.add_argument(
        "--macs",
        nargs="+",
        help="MAC addresses of multiple rings to monitor concurrently"
    )
    monitor_parser.add_argument(
        "--auto-all",
        action="store_true",
        help="Auto-detect and monitor all available rings"
    )
    monitor_parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Monitoring duration in seconds (default: 60)"
    )
    
    # DISCOVER command
    discover_parser = subparsers.add_parser("discover", help="Discover characteristics on a ring")
    discover_parser.set_defaults(func=cmd_discover)
    discover_parser.add_argument(
        "mac",
        help="MAC address of ring to discover"
    )
    
    # SCAN command
    scan_parser = subparsers.add_parser("scan", help="Scan for available rings")
    scan_parser.set_defaults(func=cmd_scan)
    scan_parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Scan timeout in seconds (default: 10)"
    )
    
    # Handle default command (monitor with positional arguments)
    # This allows: ring_monitor.py --mac ABC --duration 60 (without "monitor")
    # as well as: ring_monitor.py monitor --mac ABC --duration 60
    args = parser.parse_args()
    
    # If no command specified, check for monitor arguments in top level
    if not args.command:
        # Create a fake monitor command if monitor arguments are present
        if hasattr(args, 'mac') or hasattr(args, 'macs') or hasattr(args, 'auto_all'):
            args.func = cmd_monitor
        # Add default values if not present
        if not hasattr(args, 'duration'):
            args.duration = 60
    
    # If still no function, it's likely just help or an error
    if not hasattr(args, 'func'):
        # Check if trying to use old interface
        if args.mac or getattr(args, 'macs', None) or getattr(args, 'auto_all', False):
            args.func = cmd_monitor
            if not hasattr(args, 'duration'):
                args.duration = 60
        else:
            parser.print_help()
            return 1
    
    # Run the command
    try:
        result = asyncio.run(args.func(args))
        return 0 if result else 1
    except KeyboardInterrupt:
        print("\n\n⏹️  Interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


# Also support old-style direct argument passing (for backward compatibility)
# This allows: ring_monitor.py 69:9A:5D:F8:00:C0 60
if __name__ == "__main__":
    # Check if first argument looks like a MAC address (backward compatibility)
    if len(sys.argv) > 1 and ":" in sys.argv[1] and not sys.argv[1].startswith("-"):
        # Old style: ring_monitor.py MAC [DURATION] [-v]
        mac = sys.argv[1]
        duration = 60
        verbose = False
        
        # Try to parse additional arguments
        remaining_args = sys.argv[2:]
        if remaining_args and remaining_args[0].isdigit():
            duration = int(remaining_args[0])
            remaining_args = remaining_args[1:]
        
        if "-v" in remaining_args or "--verbose" in remaining_args:
            verbose = True
        
        class OldArgs:
            macs = [mac]
            duration = duration
            verbose = verbose
            log_dir = "data/logs"
            func = cmd_monitor
        
        try:
            result = asyncio.run(cmd_monitor(OldArgs()))
            sys.exit(0 if result else 1)
        except KeyboardInterrupt:
            print("\n\n⏹️  Interrupted by user")
            sys.exit(1)
    
    # Otherwise use modern argument parsing
    sys.exit(main())
