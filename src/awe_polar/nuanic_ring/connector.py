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
    
    def __init__(self, timeout=15.0, max_scan_attempts=3, max_connect_attempts=3, target_address=None):
        self.timeout = timeout
        self.max_scan_attempts = max_scan_attempts
        self.max_connect_attempts = max_connect_attempts
        self.target_address = target_address  # BLE address to connect to (e.g., "AA:BB:CC:DD:EE:FF")
        self.client = None
        self.device = None
    
    async def find_device(self):
        """Scan for Nuanic ring, retry up to max_scan_attempts times.
        If target_address is set, search for that specific device.
        """
        for attempt in range(1, self.max_scan_attempts + 1):
            print(f"[SCAN] Attempt {attempt}/{self.max_scan_attempts}...")
            
            try:
                # Quick scan - just find the device, don't wait
                devices = await BleakScanner.discover(timeout=2.0)
                
                for device in devices:
                    if not device.name or "Nuanic" not in device.name:
                        continue
                    
                    # If target address specified, only match that one
                    if self.target_address:
                        if device.address.lower() == self.target_address.lower():
                            self.device = device
                            print(f"[OK] Found target: {device.name} at {device.address}")
                            return device
                    else:
                        # No target specified, accept first available
                        self.device = device
                        print(f"[OK] Found: {device.name} at {device.address}")
                        return device
                
                if attempt < self.max_scan_attempts:
                    if self.target_address:
                        print(f"    Target {self.target_address} not found, retrying...")
                    else:
                        print("    Not found, retrying...")
                    await asyncio.sleep(1)
            
            except asyncio.CancelledError:
                # Re-raise so Ctrl+C still works
                raise
            except Exception as e:
                if attempt < self.max_scan_attempts:
                    print(f"    Scan error: {e}, retrying...")
                    await asyncio.sleep(1)
                else:
                    print(f"    Scan error: {e}")
        
        if self.target_address:
            print(f"[FAIL] Nuanic ring {self.target_address} not found")
        else:
            print("[FAIL] Nuanic ring not found")
        return None
    
    async def list_available_rings(self):
        """Scan and return list of all available Nuanic rings.
        Returns: List of dicts with 'address', 'name' keys
        """
        print("[SCAN] Discovering Nuanic rings...")
        
        try:
            devices = await BleakScanner.discover(timeout=3.0)
            
            nuanic_devices = []
            for device in devices:
                if device.name and "Nuanic" in device.name:
                    nuanic_devices.append({
                        "address": device.address,
                        "name": device.name,
                    })
            
            return nuanic_devices
        
        except asyncio.CancelledError:
            # Re-raise so Ctrl+C still works
            raise
        except Exception as e:
            print(f"[WARN] Scan error: {e}")
            return []
    
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
        """Connect to the ring and perform pairing with retry recovery."""
        await self._cleanup_client()

        for attempt in range(1, self.max_connect_attempts + 1):
            # Always refresh discovery on each connection attempt (privacy address may rotate)
            self.device = None
            if not await self.find_device():
                continue

            print(f"[CONNECT] Attempt {attempt}/{self.max_connect_attempts} to {self.device.name}...")

            try:
                self.client = BleakClient(self.device, timeout=self.timeout)
                await self.client.connect()
                print("[OK] Connected!")

                # Pair to establish encryption (required for authenticated characteristics)
                try:
                    await self.client.pair()
                    print("[OK] Paired!")
                except Exception as e:
                    print(f"[INFO] Pairing: {e}")

                return True

            except asyncio.TimeoutError:
                print(f"[WARN] Connection timeout ({self.timeout}s)")
            except Exception as e:
                print(f"[WARN] Connection error: {e}")

            await self._cleanup_client()

            if attempt < self.max_connect_attempts:
                print("[RETRY] Resetting BLE session and trying again...")
                await asyncio.sleep(1.5)

        print("[FAIL] Could not connect after retries")
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
