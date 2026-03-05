"""BLE connection and device management for Nuanic ring"""
import asyncio
import os
import subprocess
from bleak import BleakScanner, BleakClient


class NuanicConnector:
    """Handles BLE connection to Nuanic ring"""
    
    # GATT UUIDs
    BATTERY_CHARACTERISTIC = "00002a19-0000-1000-8000-00805f9b34fb"
    STRESS_CHARACTERISTIC = "468f2717-6a7d-46f9-9eb7-f92aab208bae"  # Stress + EDA (1.12 Hz)
    IMU_CHARACTERISTIC = "d306262b-c8c9-4c4b-9050-3a41dea706e5"      # Accelerometer (15.87 Hz)
    RAW_EDA_CHARACTERISTIC = "3c180fcc-bfec-4b7c-8e52-1a37f123e449"  # Raw EDA data candidate
    
    def __init__(self, timeout=15.0, max_scan_attempts=3, max_connect_attempts=3, target_address=None):
        self.timeout = timeout
        self.max_scan_attempts = max_scan_attempts
        self.max_connect_attempts = max_connect_attempts
        self.target_address = target_address  # BLE address to connect to (e.g., "AA:BB:CC:DD:EE:FF")
        self.client = None
        self.device = None
    
    async def find_device(self):
        """Scan for Nuanic ring.
        If target_address is set, search for that specific device.
        Retries automatically as part of discovery process.
        """
        search_label = f"'{self.target_address}'" if self.target_address else "(any Nuanic)"
        
        for attempt in range(1, self.max_scan_attempts + 1):
            try:
                # Quick scan - find all devices
                devices = await BleakScanner.discover(timeout=2.0)
                
                # Filter Nuanic devices
                for device in devices:
                    if not device.name or "Nuanic" not in device.name:
                        continue
                    
                    # If target address specified, only match that one
                    if self.target_address:
                        if device.address.lower() == self.target_address.lower():
                            self.device = device
                            return device
                    else:
                        # No target specified, accept first available
                        self.device = device
                        return device
                
                # Not found in this scan
                if attempt < self.max_scan_attempts:
                    await asyncio.sleep(0.5)  # Short pause between scans
            
            except asyncio.CancelledError:
                # Re-raise so Ctrl+C still works
                raise
            except Exception as e:
                if attempt < self.max_scan_attempts:
                    await asyncio.sleep(0.5)
        
        return None
    
    async def list_available_rings(self, include_device: bool = False):
        """Scan and return list of all available Nuanic rings.
        Returns: List of dicts with 'address', 'name' keys.
        If include_device=True, each dict also includes 'device' with the Bleak device object.
        """
        print("[SCAN] Discovering Nuanic rings...")
        
        try:
            devices = await BleakScanner.discover(timeout=3.0)
            
            nuanic_devices = []
            for device in devices:
                if device.name and "Nuanic" in device.name:
                    entry = {
                        "address": device.address,
                        "name": device.name,
                    }
                    if include_device:
                        entry["device"] = device
                    nuanic_devices.append(entry)
            
            return nuanic_devices
        
        except asyncio.CancelledError:
            # Re-raise so Ctrl+C still works
            raise
        except Exception as e:
            print(f"[WARN] Scan error: {e}")
            return []
    
    async def select_ring_interactive(self):
        """Interactive ring selection menu.
        
        NOTE: This is called automatically by connect() if no target_address is set.
        No need to call this manually unless you want to select before connecting.
        
        Scans for available rings and lets user choose which one to connect to.
        Updates self.target_address with the selected ring's MAC.
        
        Returns:
            str: Selected MAC address, or None if cancelled
        """
        print("\n" + "="*60)
        print("RING SELECTION")
        print("="*60)
        
        rings = await self.list_available_rings(include_device=True)
        
        if not rings:
            print("[!] No Nuanic rings found. Make sure rings are turned on.")
            return None
        
        print(f"\nFound {len(rings)} ring(s):\n")
        
        for idx, ring in enumerate(rings, 1):
            print(f"  [{idx}] {ring['name']:15} | MAC: {ring['address']}")
        
        if len(rings) == 1:
            print(f"\nAuto-selecting: {rings[0]['name']} ({rings[0]['address']})")
            self.target_address = rings[0]['address']
            self.device = rings[0].get("device")
            print("="*60 + "\n")
            return rings[0]['address']
        
        # Multiple rings - let user choose
        while True:
            try:
                choice = input(f"\nSelect ring (1-{len(rings)}) or 'q' to cancel: ").strip()
                
                if choice.lower() == 'q':
                    print("Cancelled.\n")
                    return None
                
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(rings):
                    selected = rings[choice_idx]
                    self.target_address = selected['address']
                    self.device = selected.get("device")
                    print(f"\nSelected: {selected['name']} ({selected['address']})")
                    print("="*60 + "\n")
                    return selected['address']
                else:
                    print(f"Invalid choice. Enter 1-{len(rings)}")
            except ValueError:
                print(f"Invalid input. Enter 1-{len(rings)} or 'q'")
    
    async def check_mac_address_dynamic(self, num_scans: int = 5, delay_between_scans: float = 1.0) -> dict:
        """Check if the ring has a dynamic or static MAC address.
        
        Performs multiple scans and compares MAC addresses to determine if the device
        uses a dynamic (changing) or static (constant) MAC address.
        
        Args:
            num_scans: Number of scans to perform (default: 5)
            delay_between_scans: Delay in seconds between scans (default: 1.0)
        
        Returns:
            dict with keys:
                - 'is_dynamic': bool, True if MAC address is dynamic, False if static
                - 'addresses': list of discovered MAC addresses
                - 'unique_addresses': set of unique MAC addresses
                - 'scans_performed': number of scans performed
                - 'num_unique': number of unique addresses found
                - 'confidence': str, 'high' if clear pattern, 'low' if inconclusive
        """
        print(f"\n[CHECK] Scanning for MAC address changes ({num_scans} scans, {delay_between_scans}s delay)...\n")
        
        discovered_addresses = []
        
        try:
            for scan_num in range(1, num_scans + 1):
                print(f"[SCAN {scan_num}/{num_scans}]", end=" ", flush=True)
                
                try:
                    devices = await BleakScanner.discover(timeout=3.0)
                    
                    # Find Nuanic devices
                    nuanic_found = False
                    for device in devices:
                        if device.name and "Nuanic" in device.name:
                            # If target address specified, only record that one
                            if self.target_address:
                                if device.address.lower() == self.target_address.lower():
                                    discovered_addresses.append(device.address)
                                    print(f"Found: {device.address} ({device.name})")
                                    nuanic_found = True
                                    break
                            else:
                                # Record first available Nuanic device
                                discovered_addresses.append(device.address)
                                print(f"Found: {device.address} ({device.name})")
                                nuanic_found = True
                                break
                    
                    if not nuanic_found:
                        print("Not found in this scan")
                
                except Exception as e:
                    print(f"Scan error: {e}")
                
                # Wait before next scan
                if scan_num < num_scans:
                    await asyncio.sleep(delay_between_scans)
            
            # Analyze results
            unique_addresses = list(set(discovered_addresses))
            is_dynamic = len(unique_addresses) > 1
            
            # Confidence assessment
            if not discovered_addresses:
                confidence = "low"  # No device found
            elif len(unique_addresses) == 1:
                confidence = "high"  # All scans found same address
            else:
                confidence = "high" if is_dynamic else "high"  # Clear pattern either way
            
            print(f"\n[RESULT]")
            print(f"  Unique addresses found: {len(unique_addresses)}")
            print(f"  Addresses: {unique_addresses}")
            print(f"  MAC is {'DYNAMIC' if is_dynamic else 'STATIC'}")
            print(f"  Confidence: {confidence}\n")
            
            return {
                'is_dynamic': is_dynamic,
                'addresses': discovered_addresses,
                'unique_addresses': unique_addresses,
                'scans_performed': num_scans,
                'num_unique': len(unique_addresses),
                'confidence': confidence,
            }
        
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"\n[ERROR] Check failed: {e}")
            return {
                'is_dynamic': None,
                'addresses': discovered_addresses,
                'unique_addresses': list(set(discovered_addresses)),
                'scans_performed': len(discovered_addresses),
                'num_unique': len(set(discovered_addresses)),
                'confidence': 'low',
            }
    
    async def _cleanup_client(self):
        """Best-effort cleanup of existing BLE client state."""
        if not self.client:
            return

        try:
            if self.client.is_connected:
                await self.client.disconnect()
        except Exception:
            pass
        finally:
            self.client = None

    async def connect(self):
        """Connect to Nuanic ring with automatic retry and recovery.
        
        If no target_address is set, shows interactive menu to select ring.
        
        Connection Flow:
        1. If needed, let user select which ring to connect to
        2. Scan for device (with retries)
        3. Establish BLE connection
        4. Perform pairing (if needed)
        5. Return success
        """
        await self._cleanup_client()
        
        # If no target address specified, prompt user to select
        if not self.target_address:
            selected = await self.select_ring_interactive()
            if not selected:
                print("[FAIL] No ring selected\n")
                return False
        
        search_label = f"'{self.target_address}'" if self.target_address else "(any available)"
        print(f"[INIT] Connecting to Nuanic ring {search_label}...")

        # If a concrete device object was selected from the latest scan, try it first.
        # This avoids a second scan/match cycle that can fail when BLE private MAC rotates.
        if self.device and (not self.target_address or self.device.address.lower() == self.target_address.lower()):
            print("[CONN] Trying selected device directly...", end=" ", flush=True)
            try:
                self.client = BleakClient(self.device, timeout=self.timeout)
                await self.client.connect()
                print("[OK] Connected")

                print("[PAIR] Establishing encryption...", end=" ", flush=True)
                try:
                    await self.client.pair()
                    print("[OK] Paired")
                except Exception:
                    print("[INFO] Pairing not available")

                print("\n[OK] Connection established!\n")
                return True
            except Exception as e:
                print(f"[RETRY] {e}")
                await self._cleanup_client()
        
        for attempt in range(1, self.max_connect_attempts + 1):
            # Step 1: Find device
            print(f"\n[SCAN {attempt}/{self.max_connect_attempts}] Searching for device...", end=" ", flush=True)
            if not await self.find_device():
                print("[NOT FOUND]")
                if self.target_address and attempt == 1:
                    print("[HINT] Target BLE address not seen. Ring may be using rotating/private MAC.")
                if attempt < self.max_connect_attempts:
                    print(f"[WAIT] Pausing before retry...")
                    await asyncio.sleep(1)
                continue
            
            print(f"[OK] Found: {self.device.name}")
            
            # Step 2: Connect
            print(f"[CONN {attempt}/{self.max_connect_attempts}] Connecting to BLE device...", end=" ", flush=True)
            try:
                self.client = BleakClient(self.device, timeout=self.timeout)
                await self.client.connect()
                print("[OK] Connected")
            except asyncio.TimeoutError:
                print(f"[TIMEOUT] ({self.timeout}s)")
                await self._cleanup_client()
                if attempt < self.max_connect_attempts:
                    print(f"[WAIT] Resetting BLE and retrying...")
                    await asyncio.sleep(1.5)
                continue
            except Exception as e:
                print(f"[ERROR] {e}")
                await self._cleanup_client()
                if attempt < self.max_connect_attempts:
                    print(f"[WAIT] Resetting BLE and retrying...")
                    await asyncio.sleep(1.5)
                continue
            
            # Step 3: Pair (optional)
            print(f"[PAIR {attempt}/{self.max_connect_attempts}] Establishing encryption...", end=" ", flush=True)
            try:
                await self.client.pair()
                print("[OK] Paired")
            except Exception as e:
                # Pairing may fail if already paired - this is OK
                print(f"[INFO] Pairing not available")
            
            # Success!
            print(f"\n[OK] Connection established!\n")
            return True
        
        # All attempts failed
        print(f"\n[FAIL] Could not connect after {self.max_connect_attempts} attempts\n")
        return False
    
    async def disconnect(self):
        """Disconnect from ring and unpair from Windows"""
        if self.client:
            await self._cleanup_client()
            print("[OK] Disconnected")
        
        # Unpair from Windows Bluetooth
        if self.device:
            await self._unpair_device()
    
    
    async def _unpair_device(self):
        """Remove device from Windows Bluetooth pairing.
        Uses Windows PowerShell to safely remove the pairing.
        """
        if not self.device:
            return
        
        try:
            # Convert BLE address to Windows format (remove colons)
            ble_address = self.device.address.replace(':', '')
            
            # PowerShell command to remove Bluetooth device
            ps_cmd = (
                f"Remove-Item -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\BTHPORT\\Parameters\\Keys\\*\\{ble_address}' "
                "-Force -ErrorAction SilentlyContinue; "
                f"Get-PnpDevice -FriendlyName '*{self.device.name}*' | Remove-PnpDevice -Force -ErrorAction SilentlyContinue"
            )
            
            # Run PowerShell command
            process = subprocess.Popen(
                ["powershell", "-Command", ps_cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = process.communicate(timeout=5)
            
            if process.returncode == 0 or process.returncode == 1:  # 1 = item not found (already unpaired)
                print(f"[OK] Removed {self.device.name} from Windows Bluetooth")
            else:
                print(f"[WARN] Unpair: {stderr.decode().strip() if stderr else 'Unknown error'}")
        
        except subprocess.TimeoutExpired:
            print("[WARN] Unpair timeout")
        except Exception as e:
            print(f"[WARN] Unpair error: {e}")
    
    async def read_battery(self):
        """Read battery level"""
        if not self.client:
            return None
        
        try:
            value = await self.client.read_gatt_char(self.BATTERY_CHARACTERISTIC)
            return value[0]
        except Exception as e:
            print(f"[FAIL] Battery read error: {e}")
            return None
    
    async def subscribe_to_stress(self, callback):
        """Subscribe to stress data notifications"""
        if not self.client:
            print("[FAIL] Subscription error: No client")
            return False
        
        if not self.client.is_connected:
            print("[FAIL] Subscription error: Not connected")
            return False
        
        try:
            await self.client.start_notify(self.STRESS_CHARACTERISTIC, callback)
            print("[OK] Subscribed to stress data")
            return True
        except Exception as e:
            print(f"[FAIL] Subscription error: {e}")
            return False
    
    async def subscribe_to_imu(self, callback):
        """Subscribe to IMU (accelerometer) notifications"""
        if not self.client:
            print("[FAIL] IMU subscription error: No client")
            return False
        
        if not self.client.is_connected:
            print("[FAIL] IMU subscription error: Not connected")
            return False
        
        try:
            await self.client.start_notify(self.IMU_CHARACTERISTIC, callback)
            print("[OK] Subscribed to IMU data")
            return True
        except Exception as e:
            print(f"[FAIL] IMU subscription error: {e}")
            return False
    
    async def unsubscribe_from_stress(self):
        """Unsubscribe from stress notifications"""
        if self.client:
            try:
                await self.client.stop_notify(self.STRESS_CHARACTERISTIC)
            except:
                pass
    
    async def unsubscribe_from_imu(self):
        """Unsubscribe from IMU notifications"""
        if self.client:
            try:
                await self.client.stop_notify(self.IMU_CHARACTERISTIC)
            except:
                pass

    async def subscribe_to_raw_eda(self, callback):
        """Subscribe to raw EDA data notifications"""
        if not self.client:
            print("[FAIL] Subscription error: No client")
            return False
        
        if not self.client.is_connected:
            print("[FAIL] Subscription error: Not connected")
            return False
        
        try:
            await self.client.start_notify(self.RAW_EDA_CHARACTERISTIC, callback)
            print("[OK] Subscribed to raw EDA data")
            return True
        except Exception as e:
            print(f"[FAIL] Subscription error: {e}")
            return False

    async def unsubscribe_from_raw_eda(self):
        """Unsubscribe from raw EDA notifications"""
        if self.client:
            try:
                await self.client.stop_notify(self.RAW_EDA_CHARACTERISTIC)
            except:
                pass

    async def discover_services(self):
        """Discover and print all services and characteristics."""
        if not self.client or not self.client.is_connected:
            print("[FAIL] Not connected to any device.")
            return

        print(f"\n[INFO] Discovering services for {self.device.name}...")
        for service in self.client.services:
            print(f"  [SERVICE] {service.uuid}: {service.description}")
            for char in service.characteristics:
                print(f"    [CHAR] {char.uuid}: {char.description}, Properties: {char.properties}")
        print("[INFO] Service discovery complete.\n")
