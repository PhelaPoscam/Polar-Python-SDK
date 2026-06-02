import asyncio
from polar_python import PolarDevice
from polar_python.constants import (
    PmdMeasurementType,
    PolarCharacteristic,
)


class BasePolarDevice:
    """Base class for connecting and streaming from Polar devices."""

    def __init__(self, device, **kwargs) -> None:
        self.device = device
        self.polar_device = None
        self._running = False

    async def start_notify(self) -> None:
        """Connect to device and initialize notifications."""
        self.polar_device = PolarDevice(self.device)
        await self.polar_device._client.connect()

        device_name = getattr(self.device, "name", "") or ""

        async def _subscribe_and_start():
            await self.polar_device._client.start_notify(
                PolarCharacteristic.PMD_CONTROL_POINT.value,
                self.polar_device._handle_pmd_control,
            )
            await self.polar_device._client.start_notify(
                PolarCharacteristic.PMD_DATA.value, self.polar_device._handle_pmd_data
            )
            self._running = True
            await self.start_streams()

        try:
            await _subscribe_and_start()
            print("Connected and authenticated successfully.")
        except Exception as e:
            err_str = str(e)
            if (
                "Authentication" in err_str
                or "Insufficient" in err_str
                or "(5)" in err_str
                or "-2147023673" in err_str
            ):
                print(
                    f"Device ({device_name}) requires pairing. Initiating BLE pairing/bonding..."
                )
                try:
                    print("\n" + "=" * 80)
                    print("PAIRING PIN REQUESTED!")
                    print(
                        "Please look at your device screen and Windows notifications/popups now."
                    )
                    print(
                        "Confirm/type the pairing PIN code on both the device and the PC."
                    )
                    print("=" * 80 + "\n")
                    await self.polar_device._client.pair()
                    # pair() stores bond keys in Windows registry, but the current
                    # connection is still unauthenticated. We must reconnect so Windows
                    # opens a fresh encrypted session using the new bond keys.
                    print("Pairing accepted. Re-establishing authenticated connection...")
                    await self.polar_device._client.disconnect()
                    await asyncio.sleep(1.0)
                    await self.polar_device._client.connect()
                    print("Retrying stream subscription...")
                    await _subscribe_and_start()
                    print("Connected and authenticated successfully after pairing!")
                except Exception as pair_err:
                    print(f"Failed to complete pairing: {pair_err}")
                    raise e
            elif "not found" in err_str.lower() or "FB005C81" in err_str:
                print("\n" + "=" * 60)
                print(
                    "SDK STREAM NOT ACTIVE: The device is not exposing the measurement service."
                )
                print("Please ensure SDK Sharing is active and the device is ready.")
                print("=" * 60 + "\n")
                raise e
            else:
                raise e

    async def start_streams(self) -> None:
        """To be overridden by subclasses to start their specific streams."""
        pass

    async def stop_notify(self) -> None:
        """Stop all streams and disconnect."""
        if self._running and self.polar_device:
            await self.polar_device.disconnect()
            self._running = False

    async def _get_default_settings(self, measurement_type: PmdMeasurementType) -> dict:
        """Query the device for available settings and extract the first supported value."""
        try:
            settings_obj = await self.polar_device.request_stream_settings(
                measurement_type
            )
            settings_dict = {}
            for s in settings_obj.settings:
                if s.values:
                    settings_dict[s.type] = s.values[0]
            return settings_dict
        except Exception as ex:
            print(
                f"Warning: Could not fetch settings for {measurement_type.name}: {ex}"
            )
            return {}
