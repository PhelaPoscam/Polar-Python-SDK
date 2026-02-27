"""BLE connection and device management for Nuanic ring"""
import asyncio
from bleak import BleakScanner, BleakClient


class NuanicConnector:
    """Handles BLE connection to Nuanic ring"""
    
    # GATT UUIDs
    BATTERY_CHARACTERISTIC = "00002a19-0000-1000-8000-00805f9b34fb"
    STRESS_CHARACTERISTIC = "468f2717-6a7d-46f9-9eb7-f92aab208bae"
    
    def __init__(self, timeout=15.0, max_scan_attempts=3):
        self.timeout = timeout
        self.max_scan_attempts = max_scan_attempts
        self.client = None
        self.device = None
    
    async def find_device(self):
        """Scan for Nuanic ring, retry up to max_scan_attempts times"""
        for attempt in range(1, self.max_scan_attempts + 1):
            print(f"[SCAN] Attempt {attempt}/{self.max_scan_attempts}...")
            devices = await BleakScanner.discover(timeout=5.0)
            
            for device in devices:
                if device.name and "Nuanic" in device.name:
                    self.device = device
                    print(f"[✓] Found: {device.name} at {device.address}\n")
                    return device
            
            if attempt < self.max_scan_attempts:
                print("    Not found, retrying...\n")
                await asyncio.sleep(1)
        
        print("[✗] Nuanic ring not found")
        return None
    
    async def connect(self):
        """Connect to the ring and perform pairing"""
        if not self.device:
            if not await self.find_device():
                return False
        
        print(f"[CONNECT] Connecting to {self.device.name}...")
        
        try:
            self.client = BleakClient(self.device.address, timeout=self.timeout)
            await self.client.connect()
            print("[✓] Connected!\n")
            
            # Attempt pairing
            try:
                await self.client.pair()
                print("[✓] Paired!\n")
            except Exception as e:
                print(f"[!] Pairing: {e}\n")
            
            return True
            
        except asyncio.TimeoutError:
            print(f"[✗] Connection timeout ({self.timeout}s)")
            return False
        except Exception as e:
            print(f"[✗] Connection error: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from ring"""
        if self.client:
            await self.client.disconnect()
            self.client = None
            print("[✓] Disconnected")
    
    async def read_battery(self):
        """Read battery level"""
        if not self.client:
            return None
        
        try:
            value = await self.client.read_gatt_char(self.BATTERY_CHARACTERISTIC)
            return value[0]
        except Exception as e:
            print(f"[✗] Battery read error: {e}")
            return None
    
    async def subscribe_to_stress(self, callback):
        """Subscribe to stress data notifications"""
        if not self.client:
            return False
        
        try:
            await self.client.start_notify(self.STRESS_CHARACTERISTIC, callback)
            print("[✓] Subscribed to stress data\n")
            return True
        except Exception as e:
            print(f"[✗] Subscription error: {e}")
            return False
    
    async def unsubscribe_from_stress(self):
        """Unsubscribe from stress notifications"""
        if self.client:
            try:
                await self.client.stop_notify(self.STRESS_CHARACTERISTIC)
            except:
                pass
