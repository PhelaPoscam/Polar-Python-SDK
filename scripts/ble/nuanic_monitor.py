"""Monolithic real-time monitor for Nuanic ring (IMU + Stress + EDA)."""
import argparse
import asyncio
import csv
import os
import struct
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.awe_polar.nuanic_ring.connector import NuanicConnector


class NuanicMonitor:
    """Single-entry monitor for real-time display and CSV logging."""

    def __init__(self, log_dir: str = "data/nuanic_logs", imu_refresh_packets: int = 5, clear_console: bool = True, ring_address: str = None):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.connector = NuanicConnector(target_address=ring_address)
        self.imu_refresh_packets = max(1, imu_refresh_packets)
        self.clear_console = clear_console

        self.start_time = None
        self.imu_count = 0
        self.stress_count = 0

        self.imu_file = None
        self.stress_file = None

        self.imu_buffer = deque(maxlen=10)
        self.stress_buffer = deque(maxlen=5)
        self.current_imu_layout = "unknown"

    def _parse_imu_packet(self, data):
        """Parse IMU packet with layout auto-detection.

        Supported layouts:
        - Layout A: ACC_X/ACC_Y + quality at byte 12 (no confirmed ACC_Z)
        - Layout B: ACC_X/ACC_Y/ACC_Z + quality at byte 14
        """
        if len(data) < 12:
            return None

        acc_x = struct.unpack("<h", data[8:10])[0]
        acc_y = struct.unpack("<h", data[10:12])[0]

        # Auto-detect quality location:
        # If byte 14 is zero but byte 12 has non-zero signal-like value, prefer legacy layout.
        use_quality_12 = len(data) > 12 and (len(data) <= 14 or (data[14] == 0 and data[12] > 0))

        if use_quality_12:
            quality = data[12]
            acc_z = None
            layout = "xy_q12"
        else:
            acc_z = struct.unpack("<h", data[12:14])[0] if len(data) >= 14 else None
            quality = data[14] if len(data) > 14 else 0
            layout = "xyz_q14"

        return {
            "acc_x": acc_x,
            "acc_y": acc_y,
            "acc_z": acc_z,
            "quality": quality,
            "layout": layout,
        }

    def _elapsed_seconds(self) -> float:
        if not self.start_time:
            return 0.0
        return max(0.001, (datetime.now() - self.start_time).total_seconds())

    def _create_log_files(self):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        self.imu_file = self.log_dir / f"nuanic_imu_{timestamp}.csv"
        with open(self.imu_file, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "timestamp",
                "elapsed_ms",
                "acc_x",
                "acc_y",
                "acc_z",
                "signal_quality",
                "full_packet_hex",
            ])

        self.stress_file = self.log_dir / f"nuanic_stress_{timestamp}.csv"
        with open(self.stress_file, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "timestamp",
                "elapsed_ms",
                "stress_raw",
                "stress_percent",
                "eda_hex",
                "full_packet_hex",
            ])

        print(f"[LOG] IMU file: {self.imu_file.name}")
        print(f"[LOG] Stress file: {self.stress_file.name}\n")

    def _imu_callback(self, sender, data):
        if len(data) < 12:
            return

        timestamp = datetime.now().isoformat()
        elapsed_ms = int(self._elapsed_seconds() * 1000)

        parsed = self._parse_imu_packet(data)
        if not parsed:
            return

        acc_x = parsed["acc_x"]
        acc_y = parsed["acc_y"]
        acc_z = parsed["acc_z"]
        signal_quality = parsed["quality"]
        layout = parsed["layout"]
        full_hex = data.hex()

        with open(self.imu_file, "a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                timestamp,
                elapsed_ms,
                acc_x,
                acc_y,
                acc_z if acc_z is not None else "",
                signal_quality,
                full_hex,
            ])

        self.imu_count += 1
        self.current_imu_layout = layout
        self.imu_buffer.append(
            {
                "count": self.imu_count,
                "acc_x": acc_x,
                "acc_y": acc_y,
                "acc_z": acc_z,
                "quality": signal_quality,
                "layout": layout,
            }
        )

        if self.imu_count % self.imu_refresh_packets == 0:
            self._update_display()

    def _stress_callback(self, sender, data):
        if len(data) < 15:
            return

        timestamp = datetime.now().isoformat()
        elapsed_ms = int(self._elapsed_seconds() * 1000)

        stress_raw = data[14]
        stress_percent = (stress_raw / 255) * 100
        eda_hex = data[15:].hex() if len(data) > 15 else ""
        full_hex = data.hex()

        with open(self.stress_file, "a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                timestamp,
                elapsed_ms,
                stress_raw,
                f"{stress_percent:.1f}",
                eda_hex,
                full_hex,
            ])

        eda_samples = []
        if len(data) >= 92:
            eda_bytes = data[15:92]
            eda_samples = [sample * (100 / 255) for sample in eda_bytes]

        eda_mean = sum(eda_samples) / len(eda_samples) if eda_samples else 0.0
        eda_min = min(eda_samples) if eda_samples else 0.0
        eda_max = max(eda_samples) if eda_samples else 0.0

        self.stress_count += 1
        self.stress_buffer.append(
            {
                "count": self.stress_count,
                "stress": stress_percent,
                "eda_mean": eda_mean,
                "eda_min": eda_min,
                "eda_max": eda_max,
            }
        )

        self._update_display()

    def _update_display(self):
        if self.clear_console:
            os.system("cls" if os.name == "nt" else "clear")

        elapsed = self._elapsed_seconds()
        imu_hz = self.imu_count / elapsed
        stress_hz = self.stress_count / elapsed

        print("=" * 110)
        print("NUANIC MONOLITHIC MONITOR")
        print("=" * 110)
        print(
            f"Elapsed: {elapsed:.1f}s | IMU: {self.imu_count} pkts ({imu_hz:.1f} Hz) | "
            f"Stress: {self.stress_count} pkts ({stress_hz:.1f} Hz)"
        )
        print(f"IMU Layout: {self.current_imu_layout}")
        print("=" * 110)

        print("\n📊 STRESS + EDA")
        print("-" * 110)
        if self.stress_buffer:
            print(f"{'Pkt':<6} {'Stress %':<10} {'Stress Bar':<24} {'EDA Mean (μS)':<15} {'EDA Range (μS)':<15}")
            print("-" * 110)
            for sample in list(self.stress_buffer):
                bar = "█" * min(20, int(sample["stress"] / 5))
                eda_range = sample["eda_max"] - sample["eda_min"]
                print(
                    f"#{sample['count']:<5} {sample['stress']:>6.1f}% {bar:<24} "
                    f"{sample['eda_mean']:>9.2f}      {eda_range:>9.2f}"
                )

        print("\n🏃 IMU")
        print("-" * 110)
        if self.imu_buffer:
            acc_z_header = "ACC_Z" if self.current_imu_layout == "xyz_q14" else "ACC_Z(n/a)"
            print(f"{'Pkt':<6} {'ACC_X':<9} {'ACC_Y':<9} {acc_z_header:<9} {'X Position':<27} {'Quality':<8}")
            print("-" * 110)
            for sample in list(self.imu_buffer):
                normalized = int(((sample["acc_x"] + 32768) / 65536) * 20)
                normalized = max(0, min(20, normalized))
                movement_bar = "─" * normalized + "●" + "─" * (20 - normalized)
                acc_z_display = sample["acc_z"] if sample["acc_z"] is not None else "-"
                print(
                    f"#{sample['count']:<5} {sample['acc_x']:>8} {sample['acc_y']:>8} "
                    f"{acc_z_display:>8} {movement_bar:<27} {sample['quality']:>7}"
                )

        print("\n" + "=" * 110)
        print("Press Ctrl+C to stop")
        print("=" * 110)

    async def run(self, duration_seconds=None):
        self._create_log_files()
        self.start_time = datetime.now()

        if not await self.connector.connect():
            print("[FAIL] Could not connect to ring")
            return False

        imu_ok = await self.connector.subscribe_to_imu(self._imu_callback)
        stress_ok = await self.connector.subscribe_to_stress(self._stress_callback)
        if not (imu_ok and stress_ok):
            print("[FAIL] Could not subscribe to both streams")
            await self.connector.disconnect()
            return False

        battery = await self.connector.read_battery()
        if battery is not None:
            print(f"Battery: {battery}%")

        print("[OK] Monitoring started")

        try:
            if duration_seconds is None:
                while True:
                    await asyncio.sleep(1)
            else:
                await asyncio.sleep(duration_seconds)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n[STOP] Stopping capture...")
        finally:
            await self.connector.unsubscribe_from_imu()
            await self.connector.unsubscribe_from_stress()
            await self.connector.disconnect()

        elapsed = self._elapsed_seconds()
        print("\n" + "=" * 80)
        print("SESSION COMPLETE")
        print("=" * 80)
        print(f"IMU packets: {self.imu_count} ({self.imu_count / elapsed:.2f} Hz avg)")
        print(f"Stress packets: {self.stress_count} ({self.stress_count / elapsed:.2f} Hz avg)")
        print(f"Combined: {(self.imu_count + self.stress_count) / elapsed:.2f} Hz avg")
        print(f"IMU CSV: {self.imu_file}")
        print(f"Stress CSV: {self.stress_file}")
        print("=" * 80)
        return True


async def main():
    parser = argparse.ArgumentParser(description="Monolithic Nuanic monitor (IMU + Stress + EDA)")
    parser.add_argument("--duration", type=int, default=None, help="Duration in seconds (omit for indefinite)")
    parser.add_argument("--log-dir", default="data/nuanic_logs", help="Directory to save CSV files")
    parser.add_argument("--imu-refresh", type=int, default=5, help="Refresh display every N IMU packets")
    parser.add_argument("--no-clear", action="store_true", help="Do not clear terminal on refresh")
    parser.add_argument("--ring-addr", default=None, help="BLE address of ring to connect to (e.g., AA:BB:CC:DD:EE:FF)")
    parser.add_argument("--list-rings", action="store_true", help="List all available Nuanic rings and exit")
    parser.add_argument("--docked", action="store_true", help="Auto-connect to the docked ring (if only one found)")
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

    # Handle ring selection: if multiple rings available and no --ring-addr, prompt user
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
                print(f"🔌 Docked mode: Using {rings[0]['name']} ({rings[0]['address']})\n")
            elif len(rings) == 0:
                print("\n❌ No Nuanic rings found (docked mode expected to find exactly 1)")
                return
            else:
                print(f"\n⚠️  Docked mode found {len(rings)} rings, but expected 1:")
                for i, ring in enumerate(rings, 1):
                    print(f"  {i}. {ring['name']:20} | {ring['address']}")
                print("\nPlease remove unused rings or use --ring-addr to specify\n")
                return
        elif len(rings) > 1:
            print(f"\n⚠️  Found {len(rings)} Nuanic rings:\n")
            for i, ring in enumerate(rings, 1):
                print(f"  {i}. {ring['name']:20} | {ring['address']}")
            
            while True:
                try:
                    choice = input("\nSelect ring (1-{}) or press Enter for first ring: ".format(len(rings)))
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
