"""Quick connection test with extended timeout for Nuanic Ring."""

import asyncio
from bleak import BleakClient
import time


async def connect():
    mac = 'E3:28:5C:24:31:EA'
    print(f'\n[CONNECT] Connecting to LHB-644B07F9 (E3:28:5C:24:31:EA)...')
    print('[CONNECT] Timeout: 20 seconds (giving pairing time)\n')
    
    try:
        start = time.time()
        async with BleakClient(mac, timeout=20.0) as client:
            elapsed = time.time() - start
            print(f'✓ Connected in {elapsed:.1f} seconds!\n')
            
            services = client.services
            print('=' * 80)
            print('GATT SERVICES & CHARACTERISTICS')
            print('=' * 80 + '\n')
            
            service_count = 0
            notify_chars = []
            
            for service in services:
                service_count += 1
                print(f'Service #{service_count}: {service.description}')
                print(f'  UUID: {service.uuid}\n')
                
                for char in service.characteristics:
                    props = ", ".join(char.properties)
                    print(f'  └─ {char.description}')
                    print(f'     UUID: {char.uuid}')
                    print(f'     Properties: {props}')
                    
                    if 'notify' in char.properties:
                        print(f'     ✓ SUPPORTS NOTIFICATIONS')
                        notify_chars.append((char.uuid, char.description))
                    print()
            
            print('=' * 80)
            print(f'Summary: {service_count} services, {len(notify_chars)} notify-capable characteristics')
            print('=' * 80 + '\n')
            
            if notify_chars:
                print('📋 NOTIFY CHARACTERISTICS (potential data streams):')
                for uuid, desc in notify_chars:
                    print(f'  • {desc}')
                    print(f'    UUID: {uuid}\n')
            
    except asyncio.TimeoutError:
        print('✗ Connection timeout after 20 seconds')
        print('  - Ring may not be actively advertising')
        print('  - Ensure ring is in pairing/discovery mode')
        print('  - Try restarting the ring')
    except Exception as e:
        print(f'✗ Error: {e}')
        print(f'   Type: {type(e).__name__}')


if __name__ == "__main__":
    asyncio.run(connect())
