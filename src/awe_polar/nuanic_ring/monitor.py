"""Real-time stress monitoring and data parsing"""
from datetime import datetime
from .connector import NuanicConnector


class NuanicMonitor:
    """Monitors and decodes Nuanic ring stress data"""
    
    def __init__(self):
        self.connector = NuanicConnector()
        self.current_stress = None
        self.current_eda_raw = None
    
    def parse_stress_packet(self, data):
        """Parse 92-byte stress packet
        
        Returns:
            dict: {
                'timestamp': datetime,
                'stress_raw': int (0-255),
                'stress_percent': float (0-100),
                'eda_raw': bytes (electrodermal activity),
                'full_data': bytes
            }
        """
        if len(data) < 15:
            return None
        
        # Byte 14 = DNE stress (0-255)
        stress_raw = data[14]
        stress_percent = (stress_raw / 255) * 100
        
        # Bytes 0-8: Header (timestamp/counter)
        # Bytes 9-13: Sensor readings
        # Bytes 15-91: EDA and other features
        eda_raw = data[15:] if len(data) > 15 else bytes()
        
        return {
            'timestamp': datetime.now(),
            'stress_raw': stress_raw,
            'stress_percent': stress_percent,
            'eda_raw': eda_raw.hex(),
            'full_data': data.hex()
        }
    
    def notification_callback(self, sender, data):
        """Handle incoming notifications"""
        parsed = self.parse_stress_packet(data)
        if parsed:
            self.current_stress = parsed['stress_percent']
            self.current_eda_raw = parsed['eda_raw']
    
    async def start_monitoring(self):
        """Connect to ring and start monitoring"""
        if not await self.connector.connect():
            return False
        
        battery = await self.connector.read_battery()
        if battery:
            print(f"Battery: {battery}%\n")
        
        return await self.connector.subscribe_to_stress(self.notification_callback)
    
    async def stop_monitoring(self):
        """Stop monitoring and disconnect"""
        await self.connector.unsubscribe_from_stress()
        await self.connector.disconnect()
    
    def get_current_stress(self):
        """Get latest stress percentage"""
        return self.current_stress
    
    def get_current_eda(self):
        """Get latest EDA raw data"""
        return self.current_eda_raw
