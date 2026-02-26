"""
Asynchronous BLE Ring Data Streamer

A complete script to:
1. Scan for and identify smart ring devices (Moodmetric, Nuanic)
2. Map GATT Services and Characteristics
3. Stream physiological data and log to CSV with timestamps

Author: AWE Polar Project
Date: 2026-02-26
"""

import asyncio
import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

# ============================================================================
# CONFIGURATION
# ============================================================================

# Target device names to search for
TARGET_DEVICE_NAMES = ["Moodmetric", "Nuanic", "LHB"]

# Characteristic UUID to subscribe to (fill in with actual UUID)
# Nuanic Ring: 00001524-1212-efde-1523-785feabcd124 (custom physiological data stream)
TARGET_CHARACTERISTIC_UUID = "00001524-1212-efde-1523-785feabcd124"

# CSV output file
OUTPUT_CSV = "data/logs/ring_data_log.csv"
CSV_HEADERS = ["timestamp", "raw_data_hex", "raw_data_bytes"]

# Connection timeout (seconds)
CONNECTION_TIMEOUT = 10.0

# Scan timeout (seconds)
SCAN_TIMEOUT = 5.0


# ============================================================================
# PHASE 1: SCAN AND IDENTIFY
# ============================================================================

async def scan_for_ring_device() -> Optional[BLEDevice]:
    """
    Scan the local environment for BLE devices.
    
    Returns the BLEDevice object if a device matching TARGET_DEVICE_NAMES is found,
    otherwise returns None.
    
    Returns:
        Optional[BLEDevice]: The discovered device or None if not found.
    """
    print(f"\n[SCAN] Searching for devices with names: {TARGET_DEVICE_NAMES}")
    print(f"[SCAN] Scanning for {SCAN_TIMEOUT} seconds...")
    
    try:
        devices = await BleakScanner.discover(timeout=SCAN_TIMEOUT)
        
        if not devices:
            print("[SCAN] No BLE devices found.")
            return None
        
        print(f"[SCAN] Found {len(devices)} device(s).\n")
        
        for device in devices:
            print(f"  • {device.name or 'Unknown'} | MAC: {device.address}")
            
            # Check if device name matches target
            if device.name and any(target in device.name for target in TARGET_DEVICE_NAMES):
                print(f"\n[SCAN] ✓ TARGET DEVICE FOUND!")
                print(f"       Name: {device.name}")
                print(f"       MAC:  {device.address}")
                return device
        
        print(f"\n[SCAN] No device found matching {TARGET_DEVICE_NAMES}")
        return None
        
    except Exception as e:
        print(f"[SCAN] Error during scan: {e}")
        return None


# ============================================================================
# PHASE 2: MAP THE ARCHITECTURE (GATT Services & Characteristics)
# ============================================================================

async def discover_gatt_architecture(client: BleakClient) -> None:
    """
    Connect to the device and print all available GATT Services and Characteristics.
    
    Args:
        client: Active BleakClient connected to the device.
    """
    print("\n[DISCOVERY] === GATT ARCHITECTURE ===\n")
    
    try:
        # Get all services
        services = client.services
        
        service_count = 0
        for service in services:
            service_count += 1
        
        print(f"Found {service_count} Service(s):\n")
        
        for service in services:
            print(f"Service: {service.description}")
            print(f"  UUID: {service.uuid}")
            print(f"  Characteristics: {len(service.characteristics)}")
            
            for char in service.characteristics:
                properties_str = ", ".join(char.properties)
                print(f"    └─ {char.description}")
                print(f"       UUID: {char.uuid}")
                print(f"       Properties: {properties_str}")
                
                # Check if this characteristic supports notifications
                if "notify" in char.properties:
                    print(f"       → SUPPORTS NOTIFICATIONS")
                
                print()
        
    except Exception as e:
        print(f"[DISCOVERY] Error mapping GATT architecture: {e}")
        raise


# ============================================================================
# PHASE 3: STREAM AND SAVE DATA
# ============================================================================

class RingDataLogger:
    """Handles CSV logging of ring physiological data."""
    
    def __init__(self, filepath: str = OUTPUT_CSV):
        """
        Initialize the logger and create CSV file if it doesn't exist.
        
        Args:
            filepath: Path to the CSV output file.
        """
        self.filepath = Path(filepath)
        self._initialize_csv()
    
    def _initialize_csv(self) -> None:
        """Create CSV file and write headers if it doesn't exist."""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        if not self.filepath.exists():
            with open(self.filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADERS)
            print(f"\n[LOG] Created CSV file: {self.filepath}")
        else:
            print(f"\n[LOG] Using existing CSV file: {self.filepath}")
    
    def log_data(self, data: bytes) -> None:
        """
        Append data entry to CSV with timestamp.
        
        Args:
            data: Raw byte data from the characteristic.
        """
        try:
            timestamp = datetime.now().isoformat()
            data_hex = data.hex()
            data_bytes = str(list(data))
            
            with open(self.filepath, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, data_hex, data_bytes])
        
        except Exception as e:
            print(f"[LOG] Error writing to CSV: {e}")


class Notificationhandler:
    """Manages notification callbacks and data logging."""
    
    def __init__(self, logger: RingDataLogger):
        """
        Initialize the handler.
        
        Args:
            logger: RingDataLogger instance for CSV output.
        """
        self.logger = logger
        self.notification_count = 0
    
    def callback(self, sender, data: bytes) -> None:
        """
        Callback handler for BLE notifications.
        
        Args:
            sender: The characteristic UUID that sent the notification.
            data: Raw byte data from the characteristic.
        """
        self.notification_count += 1
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # Print to terminal
        print(f"[{timestamp}] Notification #{self.notification_count}")
        print(f"  Characteristic: {sender}")
        print(f"  Raw (hex): {data.hex()}")
        print(f"  Raw (bytes): {list(data)}")
        print()
        
        # Log to CSV
        self.logger.log_data(data)


async def stream_ring_data(
    device: BLEDevice,
    characteristic_uuid: str = TARGET_CHARACTERISTIC_UUID
) -> None:
    """
    Connect to the device and stream data from a specific characteristic.
    
    Subscribes to notifications on the target characteristic and logs
    incoming data to CSV. Gracefully handles disconnection.
    
    Args:
        device: The BLEDevice to connect to.
        characteristic_uuid: UUID of the characteristic to subscribe to.
    
    Raises:
        TimeoutError: If connection times out.
        ValueError: If characteristic UUID is invalid or not found.
    """
    if characteristic_uuid == "insert-uuid-here":
        raise ValueError(
            "TARGET_CHARACTERISTIC_UUID is not configured. "
            "Please update the value in the script."
        )
    
    client = None
    logger = RingDataLogger()
    handler = Notificationhandler(logger)
    
    try:
        print(f"\n[STREAM] Connecting to {device.name} ({device.address})...")
        print(f"[STREAM] Timeout: {CONNECTION_TIMEOUT}s")
        
        async with BleakClient(device.address, timeout=CONNECTION_TIMEOUT) as client:
            if not client.is_connected:
                raise RuntimeError("Failed to establish connection.")
            
            print(f"[STREAM] ✓ Connected!")
            
            # Discover GATT architecture
            await discover_gatt_architecture(client)
            
            # Activate streaming on the ring before subscribing
            print(f"\n[STREAM] Sending activation command to: {characteristic_uuid}")
            activation_payloads = [
                bytes([0x01]),
                bytes([0x01, 0x01]),
                bytes([0x02]),
                bytes([0x03]),
            ]
            activation_sent = False
            for payload in activation_payloads:
                try:
                    await client.write_gatt_char(characteristic_uuid, payload, response=False)
                    activation_sent = True
                    print(f"[STREAM] ✓ Activation sent: {payload.hex()}")
                except Exception as e:
                    print(f"[STREAM] ✗ Activation failed ({payload.hex()}): {e}")

            if not activation_sent:
                raise ValueError("Failed to send activation command to ring.")

            # Subscribe to target characteristic
            print(f"\n[STREAM] Subscribing to characteristic: {characteristic_uuid}")
            try:
                await client.start_notify(characteristic_uuid, handler.callback)
                print("[STREAM] ✓ Subscribed! Waiting for data...\n")
            except Exception as e:
                raise ValueError(
                    f"Failed to subscribe to characteristic {characteristic_uuid}: {e}"
                )
            
            # Keep streaming until interrupted
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("\n[STREAM] Interrupt signal received. Unsubscribing...")
                await client.stop_notify(characteristic_uuid)
                print(f"[STREAM] ✓ Unsubscribed. Total notifications: {handler.notification_count}")
    
    except asyncio.TimeoutError:
        print(f"[STREAM] ✗ Connection timeout after {CONNECTION_TIMEOUT}s")
        raise
    except ValueError as e:
        print(f"[STREAM] ✗ Configuration error: {e}")
        raise
    except Exception as e:
        print(f"[STREAM] ✗ Unexpected error: {e}")
        raise
    finally:
        if client:
            if client.is_connected:
                await client.disconnect()
                print("[STREAM] ✓ Disconnected")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def main() -> None:
    """
    Main entry point orchestrating the three-phase workflow.
    
    1. Scan and identify the target device
    2. Map GATT architecture
    3. Stream and log data
    """
    print("=" * 70)
    print("BLE RING DATA STREAMER v1.0")
    print("=" * 70)
    
    try:
        # Phase 1: Scan
        device = await scan_for_ring_device()
        if not device:
            print("\n[MAIN] Exiting: No target device found.")
            return
        
        # Phase 2 & 3: Connect and Stream
        await stream_ring_data(device)
        
    except KeyboardInterrupt:
        print("\n[MAIN] Keyboard interrupt. Exiting gracefully...")
    except Exception as e:
        print(f"\n[MAIN] Fatal error: {e}")
        raise


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
