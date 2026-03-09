"""Real-time monitor for Nuanic ring streams (IMU + Stress + EDA)."""

import asyncio
import csv
import os
import struct
from collections import deque
from datetime import datetime
from pathlib import Path

from .connector import NuanicConnector


class NuanicMonitor:
    """Single-entry monitor for real-time display and CSV logging."""

    def __init__(
        self,
        log_dir: str = "data/nuanic_logs",
        imu_refresh_packets: int = 5,
        clear_console: bool = True,
        enable_logging: bool = True,
    ):
        self.log_dir = Path(log_dir)
        self.enable_logging = enable_logging
        if self.enable_logging:
            self.log_dir.mkdir(parents=True, exist_ok=True)

        self.connector = NuanicConnector()  # Ring selection happens at connection time
        self.imu_refresh_packets = max(1, imu_refresh_packets)
        self.clear_console = clear_console

        self.start_time = None
        self.imu_count = 0
        self.stress_count = 0

        self.current_stress = None
        self.current_eda_raw = None

        self.log_file = None

        self.imu_buffer = deque(maxlen=10)
        self.stress_buffer = deque(maxlen=5)
        self.raw_eda_buffer = deque(maxlen=10)
        self.current_imu_layout = "unknown"
        self.raw_eda_count = 0

    def _parse_imu_packet(self, data):
        """Parse IMU packet with layout auto-detection."""
        if len(data) < 12:
            return None

        acc_x = struct.unpack("<h", data[8:10])[0]
        acc_y = struct.unpack("<h", data[10:12])[0]

        use_quality_12 = len(data) > 12 and (
            len(data) <= 14 or (data[14] == 0 and data[12] > 0)
        )

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

    def parse_stress_packet(self, data):
        """Parse stress packet; backward-compatible API."""
        if len(data) < 15:
            return None

        stress_raw = data[14]
        stress_percent = (stress_raw / 255) * 100
        eda_raw = data[15:] if len(data) > 15 else bytes()

        return {
            "timestamp": datetime.now(),
            "stress_raw": stress_raw,
            "stress_percent": stress_percent,
            "eda_raw": eda_raw.hex(),
            "full_data": data.hex(),
        }

    async def check_ring_mac_address(self, num_scans: int = 5):
        """Check if ring(s) have dynamic or static MAC addresses.

        Useful for diagnosing connection issues.
        """
        result = await self.connector.check_mac_address_dynamic(num_scans=num_scans)
        return result

    def _elapsed_seconds(self) -> float:
        if not self.start_time:
            return 0.0
        return max(0.001, (datetime.now() - self.start_time).total_seconds())

    def _create_log_files(self):
        if not self.enable_logging:
            self.log_file = None
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        self.log_file = self.log_dir / f"nuanic_{timestamp}.csv"
        with open(self.log_file, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    "timestamp",
                    "elapsed_ms",
                    "data_type",
                    "acc_x",
                    "acc_y",
                    "acc_z",
                    "imu_quality",
                    "stress_raw",
                    "stress_percent",
                    "eda_hex",
                    "full_packet_hex",
                ]
            )

        print(f"[LOG] Created: {self.log_file.name}\n")

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

        if self.enable_logging and self.log_file:
            with open(self.log_file, "a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(
                    [
                        timestamp,
                        elapsed_ms,
                        "IMU",
                        acc_x,
                        acc_y,
                        acc_z if acc_z is not None else "",
                        signal_quality,
                        "",
                        "",
                        "",
                        full_hex,
                    ]
                )

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

    def _raw_eda_callback(self, sender, data):
        """Callback for raw EDA data stream."""
        timestamp = datetime.now().isoformat()
        elapsed_ms = int(self._elapsed_seconds() * 1000)
        raw_hex = data.hex()

        if self.enable_logging and self.log_file:
            with open(self.log_file, "a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(
                    [
                        timestamp,
                        elapsed_ms,
                        "RAW_EDA",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        raw_hex,
                        raw_hex,
                    ]
                )

        self.raw_eda_count += 1
        self.raw_eda_buffer.append(
            {
                "count": self.raw_eda_count,
                "data": raw_hex,
            }
        )

    def notification_callback(self, sender, data):
        """Backward-compatible stress callback API."""
        parsed = self.parse_stress_packet(data)
        if parsed:
            self.current_stress = parsed["stress_percent"]
            self.current_eda_raw = parsed["eda_raw"]

    def _stress_callback(self, sender, data):
        if len(data) < 15:
            return

        timestamp = datetime.now().isoformat()
        elapsed_ms = int(self._elapsed_seconds() * 1000)

        stress_raw = data[14]
        stress_percent = (stress_raw / 255) * 100
        eda_hex = data[15:].hex() if len(data) > 15 else ""
        full_hex = data.hex()

        if self.enable_logging and self.log_file:
            with open(self.log_file, "a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(
                    [
                        timestamp,
                        elapsed_ms,
                        "STRESS",
                        "",
                        "",
                        "",
                        "",
                        stress_raw,
                        f"{stress_percent:.1f}",
                        eda_hex,
                        full_hex,
                    ]
                )

        eda_samples = []
        if len(data) >= 92:
            eda_bytes = data[15:92]
            eda_samples = [sample * (100 / 255) for sample in eda_bytes]

        eda_mean = sum(eda_samples) / len(eda_samples) if eda_samples else 0.0
        eda_min = min(eda_samples) if eda_samples else 0.0
        eda_max = max(eda_samples) if eda_samples else 0.0

        self.stress_count += 1
        self.current_stress = stress_percent
        self.current_eda_raw = eda_hex
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
        raw_eda_hz = self.raw_eda_count / elapsed

        print("=" * 110)
        print("NUANIC MONOLITHIC MONITOR")
        print("=" * 110)
        print(
            f"Elapsed: {elapsed:.1f}s | IMU: {self.imu_count} pkts ({imu_hz:.1f} Hz) | "
            f"Stress: {self.stress_count} pkts ({stress_hz:.1f} Hz) | "
            f"Raw EDA: {self.raw_eda_count} pkts ({raw_eda_hz:.1f} Hz)"
        )
        print(f"IMU Layout: {self.current_imu_layout}")
        print("=" * 110)

        print("\n[STRESS DATA] STRESS + EDA")
        print("-" * 110)
        if self.stress_buffer:
            print(
                f"{'Pkt':<6} {'Stress %':<10} {'Stress Bar':<24} {'EDA Mean (μS)':<15} {'EDA Range (μS)':<15}"
            )
            print("-" * 110)
            for sample in list(self.stress_buffer):
                bar = "█" * min(20, int(sample["stress"] / 5))
                eda_range = sample["eda_max"] - sample["eda_min"]
                print(
                    f"#{sample['count']:<5} {sample['stress']:>6.1f}% {bar:<24} "
                    f"{sample['eda_mean']:>9.2f}      {eda_range:>9.2f}"
                )

        print("\n[IMU DATA] IMU")
        print("-" * 110)
        if self.imu_buffer:
            acc_z_header = (
                "ACC_Z" if self.current_imu_layout == "xyz_q14" else "ACC_Z(n/a)"
            )
            print(
                f"{'Pkt':<6} {'ACC_X':<9} {'ACC_Y':<9} {acc_z_header:<9} {'X Position':<27} {'Quality':<8}"
            )
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

    async def start_monitoring(self):
        """Backward-compatible API for stress-only monitoring."""
        if not await self.connector.connect():
            return False

        battery = await self.connector.read_battery()
        if battery is not None:
            print(f"Battery: {battery}%")

        return await self.connector.subscribe_to_stress(self.notification_callback)

    async def stop_monitoring(self):
        """Backward-compatible API for stress-only monitoring."""
        await self.connector.unsubscribe_from_stress()
        await self.connector.disconnect()

    def get_current_stress(self):
        """Get latest stress percentage."""
        return self.current_stress

    def get_current_eda(self):
        """Get latest EDA hex payload."""
        return self.current_eda_raw

    async def run(self, duration_seconds=None):
        self.start_time = datetime.now()

        if not await self.connector.connect():
            print("[FAIL] Could not connect to ring")
            return False

        # Create a log file only after successful connection.
        self._create_log_files()

        imu_ok = await self.connector.subscribe_to_imu(self._imu_callback)
        stress_ok = await self.connector.subscribe_to_stress(self._stress_callback)
        raw_eda_ok = await self.connector.subscribe_to_raw_eda(self._raw_eda_callback)
        if not (imu_ok and stress_ok and raw_eda_ok):
            print("[FAIL] Could not subscribe to all streams")
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
            await self.connector.unsubscribe_from_raw_eda()
            await self.connector.disconnect()

        elapsed = self._elapsed_seconds()
        print("\n" + "=" * 80)
        print("SESSION COMPLETE")
        print("=" * 80)
        print(f"IMU packets: {self.imu_count} ({self.imu_count / elapsed:.2f} Hz avg)")
        print(
            f"Stress packets: {self.stress_count} ({self.stress_count / elapsed:.2f} Hz avg)"
        )
        print(
            f"Raw EDA packets: {self.raw_eda_count} ({self.raw_eda_count / elapsed:.2f} Hz avg)"
        )
        print(
            f"Combined: {(self.imu_count + self.stress_count + self.raw_eda_count) / elapsed:.2f} Hz avg"
        )
        if self.enable_logging and self.log_file:
            print(f"Log CSV: {self.log_file}")
        else:
            print("Log CSV: disabled")
        print("=" * 80)
        return True
