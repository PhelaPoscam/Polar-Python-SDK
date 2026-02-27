#!/usr/bin/env python3
"""
Shared BLE utilities for Nuanic ring monitoring
Provides common functionality for ring discovery, connection, and data capture
"""
import asyncio
from bleak import BleakClient, BleakScanner
import csv
from datetime import datetime
import os
from pathlib import Path
from typing import Dict, List, Optional, Callable


class RingCharacteristics:
    """Define known Nuanic ring characteristics and their variants"""
    
    # IMU (Acceleration data) - Two hardware variants exist
    IMU_VARIANTS = [
        "d306262b-3236-4c42-9eb7-f92aab208ba8",  # Ring variant 1
        "d306262b-c8c9-4c4b-9050-3a41dea706e5",  # Ring variant 2
    ]
    
    # Stress + EDA (Physiological data) - Same across all rings
    STRESS_EDA = "468f2717-6a7d-46f9-9eb7-f92aab208bae"
    
    # All characteristics for flexible subscription
    ALL = {
        "d306262b-3236-4c42-9eb7-f92aab208ba8": "IMU",
        "d306262b-c8c9-4c4b-9050-3a41dea706e5": "IMU",
        "468f2717-6a7d-46f9-9eb7-f92aab208bae": "Stress+EDA",
    }


class RingMonitor:
    """Single Nuanic ring monitor with flexible configuration"""
    
    def __init__(self, mac_address: str, duration: int = 60, log_dir: str = "data/logs", verbose: bool = False):
        self.mac_address = mac_address
        self.duration = duration
        self.log_dir = log_dir
        self.verbose = verbose
        
        self.device = None
        self.client = None
        self.log_file = None
        self.csv_writer = None
        self.packet_count = 0
        self.start_time = None
        self.subscribed_characteristics = []
        
        # Create log directory
        Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    def _log(self, message: str, level: str = "INFO"):
        """Print log message with optional verbosity"""
        if level == "DEBUG" and not self.verbose:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = f"[{timestamp}] [{level:5s}]"
        print(f"{prefix} {message}")
    
    async def find_ring(self, timeout: int = 20) -> bool:
        """Discover the ring by MAC address"""
        self._log(f"🔍 Scanning for ring {self.mac_address}...", "INFO")
        start = datetime.now()
        attempt = 0
        
        while (datetime.now() - start).total_seconds() < timeout:
            attempt += 1
            devices = await BleakScanner.discover(timeout=5.0)
            
            self._log(f"Scan #{attempt}: Found {len(devices)} devices", "DEBUG")
            
            for device in devices:
                self._log(f"  - {device.name or 'Unknown'} @ {device.address}", "DEBUG")
                
                if device.address.upper() == self.mac_address.upper():
                    self.device = device
                    self._log(f"✅ Found: {device.name} at {device.address}", "INFO")
                    return True
            
            if attempt < 4:  # Only print dots for first few attempts
                print(".", end="", flush=True)
            await asyncio.sleep(1)
        
        self._log(f"❌ Could not find ring at {self.mac_address}", "ERROR")
        return False
    
    async def discover_characteristics(self) -> Dict[str, str]:
        """Discover all available services and characteristics on the ring"""
        if not self.device:
            self._log("⚠️  Ring not found. Call find_ring() first", "ERROR")
            return {}
        
        discovered = {}
        
        try:
            async with BleakClient(self.device.address) as client:
                self._log(f"🔗 Connected for discovery", "INFO")
                
                for service in client.services:
                    self._log(f"📦 Service: {service.uuid}", "INFO")
                    
                    for char in service.characteristics:
                        self._log(f"  📡 {char.uuid}: {', '.join(char.properties)}", "DEBUG")
                        
                        # Check if it matches known characteristics
                        char_uuid = char.uuid.lower()
                        for known_uuid, char_type in RingCharacteristics.ALL.items():
                            if known_uuid in char_uuid:
                                discovered[char_uuid] = char_type
                                self._log(f"    ✓ Known: {char_type}", "INFO")
                
        except Exception as e:
            self._log(f"Error during discovery: {e}", "ERROR")
        
        return discovered
    
    async def start_monitoring(self, notification_handler: Optional[Callable] = None):
        """Connect to ring and subscribe to characteristics"""
        if not self.device:
            self._log("⚠️  Ring not found. Call find_ring() first", "ERROR")
            return False
        
        # Setup logging
        log_filename = f"{self.log_dir}/ring_{self.mac_address.replace(':', '')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.log_file = open(log_filename, 'w', newline='')
        self.csv_writer = csv.DictWriter(
            self.log_file,
            fieldnames=['timestamp', 'relative_time', 'characteristic', 'data_length']
        )
        self.csv_writer.writeheader()
        
        self.start_time = datetime.now()
        
        # Use default handler if none provided
        if notification_handler is None:
            notification_handler = self._default_notification_handler
        
        try:
            async with BleakClient(self.device.address) as client:
                self._log(f"🔗 Connected to {self.device.name}", "INFO")
                
                # Try to subscribe to available characteristics
                for char_uuid in RingCharacteristics.ALL.keys():
                    try:
                        await client.start_notify(char_uuid, notification_handler)
                        char_type = RingCharacteristics.ALL[char_uuid]
                        self.subscribed_characteristics.append(char_uuid)
                        self._log(f"📡 Subscribed to {char_type}", "INFO")
                    except Exception as e:
                        self._log(f"  ⚠️  Could not subscribe to {char_uuid[:8]}...: {str(e)[:50]}", "DEBUG")
                
                if not self.subscribed_characteristics:
                    self._log("❌ Could not subscribe to any characteristics!", "ERROR")
                    return False
                
                self._log(f"🚀 Monitoring for {self.duration}s...\n", "INFO")
                
                # Monitor for specified duration
                while (datetime.now() - self.start_time).total_seconds() < self.duration:
                    await asyncio.sleep(0.1)
        
        except Exception as e:
            self._log(f"❌ Error: {e}", "ERROR")
            return False
        
        finally:
            if self.log_file:
                self.log_file.close()
            self._print_summary()
        
        return True
    
    async def _default_notification_handler(self, sender, data):
        """Default notification handler - logs data"""
        if not self.start_time:
            return
        
        timestamp = datetime.now()
        relative_time = (timestamp - self.start_time).total_seconds()
        
        # Identify characteristic
        char_uuid = str(sender).lower()
        char_type = "Unknown"
        for uuid_key, uuid_name in RingCharacteristics.ALL.items():
            if uuid_key in char_uuid:
                char_type = uuid_name
                break
        
        # Print first packets
        if self.packet_count < 50:
            self._log(f"  #{self.packet_count+1:3d} | {relative_time:6.2f}s | {char_type:10s} | {len(data):2d} bytes", "INFO")
        
        # Log to file
        if self.csv_writer:
            self.csv_writer.writerow({
                'timestamp': timestamp.isoformat(),
                'relative_time': f'{relative_time:.3f}',
                'characteristic': char_type,
                'data_length': len(data),
            })
            self.log_file.flush()
        
        self.packet_count += 1
        
        # Print progress
        if self.packet_count > 0 and self.packet_count % 100 == 0:
            rate = self.packet_count / relative_time if relative_time > 0 else 0
            self._log(f"📊 {self.packet_count:5d} packets | {relative_time:6.2f}s | {rate:5.1f} Hz", "INFO")
    
    def _print_summary(self):
        """Print monitoring summary"""
        if not self.start_time:
            return
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        rate = self.packet_count / elapsed if elapsed > 0 else 0
        
        print()
        print("=" * 80)
        print("📊 MONITORING COMPLETE")
        print("=" * 80)
        print(f"Ring:    {self.mac_address}")
        print(f"Packets: {self.packet_count:5d}")
        print(f"Time:    {elapsed:6.1f}s")
        print(f"Rate:    {rate:6.1f} Hz")
        if self.log_file and hasattr(self.log_file, 'name'):
            print(f"Log:     {self.log_file.name}")
        print("=" * 80)


class MultiRingMonitor:
    """Monitor multiple Nuanic rings concurrently"""
    
    def __init__(self, mac_addresses: List[str], duration: int = 60, log_dir: str = "data/logs", verbose: bool = False):
        self.mac_addresses = mac_addresses
        self.duration = duration
        self.log_dir = log_dir
        self.verbose = verbose
        
        self.monitors = [RingMonitor(mac, duration, log_dir, verbose) for mac in mac_addresses]
        self.log_file = None
        self.csv_writer = None
        self.packet_counts = {mac: 0 for mac in mac_addresses}
        self.start_time = None
    
    def _log(self, message: str, level: str = "INFO"):
        """Print log message"""
        if level == "DEBUG" and not self.verbose:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level:5s}] {message}")
    
    async def find_all_rings(self, timeout: int = 30) -> bool:
        """Find all rings"""
        self._log(f"🔍 Searching for {len(self.mac_addresses)} ring(s)...", "INFO")
        
        # Find all rings concurrently
        results = await asyncio.gather(
            *[monitor.find_ring(timeout) for monitor in self.monitors],
            return_exceptions=True
        )
        
        found = sum(1 for r in results if r is True)
        
        if found == len(self.mac_addresses):
            self._log(f"✅ Found all {found} ring(s)", "INFO")
            return True
        else:
            self._log(f"⚠️  Found only {found}/{len(self.mac_addresses)} ring(s)", "WARNING")
            return found > 0
    
    async def start_monitoring(self):
        """Monitor all rings concurrently"""
        # Setup logging
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)
        log_filename = f"{self.log_dir}/multi_ring_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.log_file = open(log_filename, 'w', newline='')
        self.csv_writer = csv.DictWriter(
            self.log_file,
            fieldnames=['timestamp', 'relative_time', 'ring_mac', 'characteristic', 'data_length']
        )
        self.csv_writer.writeheader()
        
        self.start_time = datetime.now()
        
        self._log(f"🚀 Starting concurrent monitoring for {self.duration}s...\n", "INFO")
        
        # Create custom handler for multi-ring logging
        async def multi_handler(ring_mac):
            async def handler(sender, data):
                if not self.start_time:
                    return
                
                timestamp = datetime.now()
                relative_time = (timestamp - self.start_time).total_seconds()
                
                char_uuid = str(sender).lower()
                char_type = "Unknown"
                for uuid_key, uuid_name in RingCharacteristics.ALL.items():
                    if uuid_key in char_uuid:
                        char_type = uuid_name
                        break
                
                self.packet_counts[ring_mac] += 1
                
                if self.csv_writer:
                    self.csv_writer.writerow({
                        'timestamp': timestamp.isoformat(),
                        'relative_time': f'{relative_time:.3f}',
                        'ring_mac': ring_mac,
                        'characteristic': char_type,
                        'data_length': len(data),
                    })
                    self.log_file.flush()
                
                # Print summary every 100 packets total
                total = sum(self.packet_counts.values())
                if total > 0 and total % 100 == 0:
                    summary = " | ".join([f"{m.split(':')[-2:][0]}{m.split(':')[-1]}: {count}" 
                                         for m, count in self.packet_counts.items()])
                    self._log(f"📊 {relative_time:6.1f}s | {summary}", "INFO")
            
            return handler
        
        try:
            # Start monitoring on all rings concurrently
            tasks = []
            for monitor, mac in zip(self.monitors, self.mac_addresses):
                handler = await multi_handler(mac)
                tasks.append(monitor.start_monitoring(handler))
            
            await asyncio.gather(*tasks, return_exceptions=True)
        
        finally:
            if self.log_file:
                self.log_file.close()
            self._print_summary()
    
    def _print_summary(self):
        """Print monitoring summary for all rings"""
        elapsed = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        
        print()
        print("=" * 80)
        print("📊 MULTI-RING MONITORING COMPLETE")
        print("=" * 80)
        
        for mac, count in self.packet_counts.items():
            rate = count / elapsed if elapsed > 0 else 0
            print(f"Ring {mac}: {count:5d} packets ({rate:5.1f} Hz)")
        
        total = sum(self.packet_counts.values())
        print(f"Total:     {total:5d} packets in {elapsed:.1f}s")
        
        if self.log_file and hasattr(self.log_file, 'name'):
            print(f"Log:       {self.log_file.name}")
        print("=" * 80)


async def scan_for_rings(timeout: int = 10) -> List[str]:
    """Scan for all available Nuanic rings and return their MAC addresses"""
    print(f"🔍 Scanning for Nuanic rings (max {timeout}s)...\n")
    
    rings = {}
    start = datetime.now()
    attempt = 0
    
    while (datetime.now() - start).total_seconds() < timeout:
        attempt += 1
        devices = await BleakScanner.discover(timeout=5.0)
        
        for device in devices:
            if device.name and device.name.lower() == "nuanic":
                if device.address not in rings:
                    rings[device.address] = device
                    print(f"  ✅ Ring #{len(rings)}: {device.address}")
        
        if len(rings) > 0:
            await asyncio.sleep(0.5)  # Brief wait before returning
            break
        
        print(".", end="", flush=True)
        await asyncio.sleep(1)
    
    print()
    return list(rings.keys())
