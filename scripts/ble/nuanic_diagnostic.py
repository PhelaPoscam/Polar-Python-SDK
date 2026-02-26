"""
Advanced Nuanic Ring Diagnostic Script

Attempts to:
1. Send activation/request commands via write characteristics
2. Read from all characteristics
3. Monitor all notify channels simultaneously
4. Capture raw EDA data format
"""

import asyncio
from bleak import BleakScanner, BleakClient
from datetime import datetime
import struct


async def nuanic_diagnostic():
    """Comprehensive diagnostic of Nuanic ring data transmission."""
    
    print("\n[DIAGNOSTIC] Scanning for Nuanic ring...")
    devices = await BleakScanner.discover(timeout=5.0)
    
    ring = None
    for device in devices:
        if device.name and ("LHB" in device.name or "Nuanic" in device.name):
            ring = device
            break
    
    if not ring:
        print("✗ Ring not found")
        return
    
    print(f"✓ Found: {ring.name} ({ring.address})\n")
    
    try:
        async with BleakClient(ring.address, timeout=45.0) as client:
            print("✓ Connected!\n")
            
            # Collect all characteristics
            all_chars = {}
            write_chars = []
            notify_chars = []
            read_chars = []
            
            print("[DIAGNOSTIC] Cataloging characteristics...\n")
            
            for service in client.services:
                for char in service.characteristics:
                    uuid = char.uuid
                    props = char.properties
                    all_chars[uuid] = {
                        'service': service.uuid,
                        'description': char.description or "Unknown",
                        'properties': props
                    }
                    
                    if "write" in props:
                        write_chars.append(uuid)
                    if "notify" in props:
                        notify_chars.append(uuid)
                    if "read" in props:
                        read_chars.append(uuid)
            
            print(f"Found {len(all_chars)} characteristics:")
            print(f"  • {len(write_chars)} write-capable")
            print(f"  • {len(notify_chars)} notify-capable")
            print(f"  • {len(read_chars)} read-capable\n")
            
            # Try reading from all readable characteristics
            print("[DIAGNOSTIC] Reading current values from readable characteristics:\n")
            for uuid in read_chars:
                try:
                    data = await client.read_gatt_char(uuid)
                    print(f"  {uuid}")
                    print(f"    Hex:   {data.hex()}")
                    print(f"    Bytes: {list(data)}")
                    print(f"    ASCII: {repr(data)}\n")
                except Exception as e:
                    print(f"  {uuid}: ✗ {e}\n")
            
            # Try writing activation commands to write characteristics
            print("[DIAGNOSTIC] Attempting write commands on writable characteristics...\n")
            test_commands = [
                ("Start", bytes([0x01])),
                ("Enable", bytes([0x01, 0x01])),
                ("Request Data", bytes([0x02])),
                ("Query", bytes([0x03])),
                ("Init", bytes([0x00, 0x01])),
            ]
            
            for uuid in write_chars:
                print(f"  {uuid}:")
                for cmd_name, cmd_bytes in test_commands:
                    try:
                        await client.write_gatt_char(uuid, cmd_bytes, response=False)
                        print(f"    ✓ Sent {cmd_name}: {cmd_bytes.hex()}")
                    except Exception as e:
                        print(f"    ✗ Failed {cmd_name}: {e}")
                print()
            
            # Set up listeners on all notify characteristics
            print("[DIAGNOSTIC] Setting up notification listeners...\n")
            
            notification_data = {}
            
            for uuid in notify_chars:
                notification_data[uuid] = {
                    'count': 0,
                    'samples': []
                }
            
            def make_callback(uuid):
                def callback(sender, data):
                    notification_data[uuid]['count'] += 1
                    notification_data[uuid]['samples'].append(data)
                    count = notification_data[uuid]['count']
                    
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    print(f"[{timestamp}] Notification #{count} on {uuid[:8]}...")
                    print(f"  Length: {len(data)} bytes")
                    print(f"  Hex:    {data.hex()}")
                    print(f"  Bytes:  {list(data)}")
                    
                    # Try to parse as EDA value
                    if len(data) >= 2:
                        try:
                            # Try unsigned 16-bit
                            val_u16 = struct.unpack('<H', data[:2])[0]
                            print(f"  Parse:  {val_u16} (uint16_le)")
                        except:
                            pass
                        try:
                            # Try signed 16-bit
                            val_s16 = struct.unpack('<h', data[:2])[0]
                            print(f"  Parse:  {val_s16} (int16_le)")
                        except:
                            pass
                        try:
                            # Try float
                            val_f = struct.unpack('<f', data[:4])[0]
                            print(f"  Parse:  {val_f:.3f} (float_le)")
                        except:
                            pass
                    print()
                
                return callback
            
            for uuid in notify_chars:
                try:
                    await client.start_notify(uuid, make_callback(uuid))
                    print(f"  ✓ Listening on {uuid}")
                except Exception as e:
                    print(f"  ✗ Failed to subscribe to {uuid}: {e}")
            
            print("\n[DIAGNOSTIC] Listening for 45 seconds...\n")
            print("=" * 70)
            
            try:
                await asyncio.sleep(45)
            except KeyboardInterrupt:
                pass
            
            print("=" * 70)
            
            # Summary
            print("\n[DIAGNOSTIC] Summary:\n")
            for uuid in notify_chars:
                count = notification_data[uuid]['count']
                print(f"  {uuid}")
                print(f"    Notifications: {count}")
                if count > 0:
                    print(f"    First sample:  {notification_data[uuid]['samples'][0].hex()}")
                    print(f"    Last sample:   {notification_data[uuid]['samples'][-1].hex()}")
                print()
            
            # Unsubscribe
            for uuid in notify_chars:
                try:
                    await client.stop_notify(uuid)
                except:
                    pass
    
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(nuanic_diagnostic())
