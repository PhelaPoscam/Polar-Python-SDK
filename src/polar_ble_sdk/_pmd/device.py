import asyncio
import contextlib
import struct
from collections.abc import Callable
from typing import TypeAlias

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice

from . import exceptions, parsers
from .constants import (
    PmdControlOperationCode,
    PmdControlPointErrorCode,
    PmdMeasurementType,
    PmdSettingType,
    PolarCharacteristic,
)
from .models import (
    ACCData,
    ECGData,
    GyroData,
    HRData,
    MAGData,
    MeasurementSettings,
    PPGData,
    PPIData,
)

# Emit a per-kind frame tally every N raw PMD notifications. Low enough to spot
# a silent stream, high enough not to flood the log panel during a session.
PMD_STATS_INTERVAL = 500


class PolarDevice:
    """A client to interface with Polar BLE devices.

    This class provides methods to connect to a Polar device, discover its available
    measurement features, and start/stop various data streams (e.g., ECG, ACC, HR)
    using asynchronous callbacks.

    Note:
        Currently, this library has only been tested on and is guaranteed to work
        with the **Polar H10** and **Polar Verity Sense** devices.
    """

    ECGCallback: TypeAlias = Callable[[ECGData], None]
    ACCCallback: TypeAlias = Callable[[ACCData], None]
    PPICallback: TypeAlias = Callable[[PPIData], None]
    PPGCallback: TypeAlias = Callable[[PPGData], None]
    GyroCallback: TypeAlias = Callable[[GyroData], None]
    MAGCallback: TypeAlias = Callable[[MAGData], None]
    HRCallback: TypeAlias = Callable[[HRData], None]

    _client: BleakClient
    _queue_pmd_control: asyncio.Queue
    _control_lock: asyncio.Lock
    _factors: dict[PmdMeasurementType, float]

    _ecg_callback: ECGCallback | None = None
    _acc_callback: ACCCallback | None = None
    _ppi_callback: PPICallback | None = None
    _ppg_callback: PPGCallback | None = None
    _gyro_callback: GyroCallback | None = None
    _mag_callback: MAGCallback | None = None
    _hr_callback: HRCallback | None = None

    def __init__(
        self,
        address_or_ble_device: str | BLEDevice,
        disconnected_callback: Callable[[BleakClient], None] | None = None,
        pmd_event_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        """Initializes the PolarDevice with a BLE address or device.

        Args:
            address_or_ble_device: The Bluetooth MAC address (str) or a discovered
                BLEDevice instance of the Polar device.
            disconnected_callback: Optional Bleak hook invoked on any disconnect
                (intentional or unexpected), mirroring the vendor SDK's
                onDeviceDisconnected reason callback.
            pmd_event_callback: Optional sink for diagnostic events on the PMD
                data path (parse errors, periodic frame-count summaries).
                Signature matches ``BasePolarDevice._emit`` (msg, severity).
        """
        self._client = BleakClient(
            address_or_ble_device, disconnected_callback=disconnected_callback
        )
        self._queue_pmd_control = asyncio.Queue()
        self._control_lock = asyncio.Lock()
        self._factors = {}
        self._pmd_event_cb = pmd_event_callback
        self._pmd_counts: dict[str, int] = {}

    async def connect(self) -> None:
        """Connects to the Polar BLE device and sets up initial notifications.

        Establishes the Bluetooth connection and starts listening to the PMD control
        point and PMD data characteristics.
        """
        await self._client.connect()
        try:
            await self._client.start_notify(
                PolarCharacteristic.PMD_CONTROL_POINT.value, self._handle_pmd_control
            )
            await self._client.start_notify(
                PolarCharacteristic.PMD_DATA.value, self._handle_pmd_data
            )
        except BaseException:
            # __aexit__ never runs when __aenter__ raises; don't leak the link.
            with contextlib.suppress(Exception):
                await self._client.disconnect()
            raise

    def _drain_control_queue(self) -> None:
        """Drop queued control-point replies, e.g. a late reply to a timed-out request."""
        while not self._queue_pmd_control.empty():
            try:
                self._queue_pmd_control.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def disconnect(self) -> None:
        """Disconnects from the Polar BLE device."""
        self._drain_control_queue()
        await self._client.disconnect()

    async def __aenter__(self):
        """Asynchronous context manager entry point.

        Returns:
            PolarDevice: The connected device instance.
        """
        await self.connect()
        return self

    async def __aexit__(self, _unused_exc_type, _unused_exc_val, _unused_exc_tb):
        """Asynchronous context manager exit point."""
        await self.disconnect()

    async def get_available_features(self) -> list[PmdMeasurementType]:
        """Retrieves the available measurement features from the Polar device.

        Queries the PMD control point to determine which sensor streams (e.g., ECG,
        ACC, PPG) are supported by the currently connected device.

        Returns:
            A list of supported PmdMeasurementType enums.

        Raises:
            exceptions.ControlPointResponseError: If the device returns an unexpected
                response format.
        """
        data = await self._client.read_gatt_char(
            PolarCharacteristic.PMD_CONTROL_POINT.value
        )
        if data[0] != 0x0F:
            raise exceptions.ControlPointResponseError(
                "Unexpected response from the control point"
            )
        features = data[1]
        results: list[PmdMeasurementType] = []
        for i in range(8):
            if features & (1 << i):
                with contextlib.suppress(ValueError):
                    results.append(PmdMeasurementType(i))
        return results

    async def _read_control_response(
        self,
        op: int,
        measurement_type: int | None = None,
        timeout: float = 5.0,
    ) -> bytearray | None:
        """Await the control-point reply matching ``op`` and ``measurement_type``.

        Replies are only removed from the queue when a caller reads them, so
        commands that ignore their reply (SDK mode, stop) leave one behind. A
        blind ``queue.get()`` then reads that stale reply as its own, pairing
        every later request with the response to the one before it. That is how
        an ACC start rejected for missing channels was reported as success: the
        SDK-mode reply poisoned the settings fetch, and the GET reply was then
        read as the START reply. Matching on the response header discards
        mismatched replies and keeps waiting, so pairing stays correct whatever
        is queued.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            try:
                response = await asyncio.wait_for(
                    self._queue_pmd_control.get(), remaining
                )
            except asyncio.TimeoutError:
                return None
            if (
                len(response) >= 3
                and response[0] == 0xF0
                and response[1] == op
                and (measurement_type is None or response[2] == measurement_type)
            ):
                return await self._read_continuations(response, deadline)

    async def _read_continuations(
        self, first: bytearray, deadline: float
    ) -> bytearray | None:
        """Append continuation packets while the reply's "more" flag is set.

        As in the official Polar SDK, byte 4 of the first packet and byte 0 of
        each continuation say whether another packet follows; a continuation's
        payload starts at byte 1. Returns None if the reply is incomplete.
        """
        merged = bytearray(first)
        more = len(merged) > 4 and merged[4] != 0
        loop = asyncio.get_running_loop()
        while more:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            try:
                part = await asyncio.wait_for(self._queue_pmd_control.get(), remaining)
            except asyncio.TimeoutError:
                return None
            if not part or part[0] == 0xF0:  # a new reply: this one was cut short
                return None
            merged += part[1:]
            more = part[0] != 0
        if len(merged) > 4:
            merged[4] = 0
        return merged

    async def request_stream_settings(
        self, measurement_type: PmdMeasurementType
    ) -> MeasurementSettings:
        """Requests the available stream settings for a specific measurement type.

        Args:
            measurement_type: The type of measurement (e.g., ECG, ACC) to query.

        Returns:
            The available measurement settings for the requested type.

        Raises:
            exceptions.ControlPointResponseError: If the device does not answer.
        """
        async with self._control_lock:
            self._drain_control_queue()
            await self._client.write_gatt_char(
                PolarCharacteristic.PMD_CONTROL_POINT.value,
                bytearray([PmdControlOperationCode.GET, measurement_type.value]),
            )
            response = await self._read_control_response(
                PmdControlOperationCode.GET, measurement_type.value
            )
            if response is None:
                raise exceptions.ControlPointResponseError(
                    f"No settings response for {measurement_type.name}"
                )
            settings = MeasurementSettings.from_bytes(response)
            if (
                settings.error_code is not None
                and settings.error_code != PmdControlPointErrorCode.SUCCESS
            ):
                raise exceptions.ControlPointResponseError(
                    f"Device rejected settings request for "
                    f"{measurement_type.name}: {settings.error_code.name}"
                )
            return settings

    async def start_stream(self, settings: MeasurementSettings) -> None:
        """Starts a generic PMD stream based on the provided settings.

        Writes the configuration to the device and extracts necessary calculation factors
        from the response if they are provided.

        Args:
            settings: The measurement settings configuration to apply.

        Raises:
            exceptions.ControlPointResponseError: If the device does not answer,
                or rejects the requested settings.
        """
        async with self._control_lock:
            self._drain_control_queue()
            await self._client.write_gatt_char(
                PolarCharacteristic.PMD_CONTROL_POINT.value, settings.to_bytes()
            )
            response_bytes = await self._read_control_response(
                PmdControlOperationCode.START, settings.measurement_type.value
            )
            if response_bytes is None:
                raise exceptions.ControlPointResponseError(
                    f"No start response for {settings.measurement_type.name}"
                )
            response = MeasurementSettings.from_bytes(response_bytes)
            if (
                response.error_code is not None
                and response.error_code != PmdControlPointErrorCode.SUCCESS
            ):
                raise exceptions.ControlPointResponseError(
                    f"Device rejected stream: {response.error_code.name}"
                )
            for setting in response.settings:
                if setting.type == PmdSettingType.FACTOR and setting.values:
                    raw_int_factor = setting.values[0]
                    real_factor = struct.unpack(
                        "<f", struct.pack("<I", raw_int_factor)
                    )[0]
                    self._factors[settings.measurement_type] = real_factor
                    break

    async def stop_stream(self, measurement_type: PmdMeasurementType) -> None:
        """Stops a generic PMD stream and cleans up its stored factors.

        Args:
            measurement_type: The type of measurement stream to stop.
        """
        async with self._control_lock:
            await self._client.write_gatt_char(
                PolarCharacteristic.PMD_CONTROL_POINT.value,
                bytearray([PmdControlOperationCode.STOP, measurement_type.value]),
            )
            self._factors.pop(measurement_type, None)

    # ── SDK mode (enables higher sample rates, e.g. PPG 135/176 Hz) ──────

    async def enable_sdk_mode(self) -> None:
        """Enables SDK mode on the device.

        SDK mode unlocks additional PMD settings (e.g. PPG at 135/176 Hz on the
        Verity Sense). Protocol: REQUEST_MEASUREMENT_START with the SDK_MODE
        measurement type (0x09), per the official Polar BLE SDK (which also
        sends the command without reading a response). The reply is left queued;
        ``_read_control_response`` discards replies that match no pending
        request, so it cannot desynchronise later commands.
        """
        async with self._control_lock:
            await self._client.write_gatt_char(
                PolarCharacteristic.PMD_CONTROL_POINT.value,
                bytearray([PmdControlOperationCode.START, 0x09]),
            )

    async def disable_sdk_mode(self) -> None:
        """Disables SDK mode on the device (STOP_MEASUREMENT, type 0x09)."""
        async with self._control_lock:
            await self._client.write_gatt_char(
                PolarCharacteristic.PMD_CONTROL_POINT.value,
                bytearray([PmdControlOperationCode.STOP, 0x09]),
            )

    async def sdk_mode_enabled(self) -> bool:
        """Returns True if SDK mode is currently enabled (GET_SDK_MODE_STATUS).

        Request:  [0x06] (GET_SDK_MODE_STATUS)
        Response: [0xF0, 0x06, 0x09, status, more, sdk_mode_status]
        SDK-mode status is the first parameter byte (index 5); non-zero = enabled.
        """
        async with self._control_lock:
            self._drain_control_queue()
            await self._client.write_gatt_char(
                PolarCharacteristic.PMD_CONTROL_POINT.value,
                bytearray([0x06]),  # GET_SDK_MODE_STATUS
            )
            response = await self._read_control_response(0x06, timeout=3.0)
            if response is None:
                raise asyncio.TimeoutError("No response to GET_SDK_MODE_STATUS")
            # response[0]=0xF0, response[1]=op(6), response[2]=type(9),
            # response[3]=status(0=OK), response[4]=more, response[5]=sdk_mode_status
            return len(response) > 5 and response[5] != 0

    async def start_ecg_stream(
        self, ecg_callback: ECGCallback, sample_rate: int, resolution: int
    ) -> None:
        """Starts the Electrocardiogram (ECG) data stream.

        Device Support:
            - Polar H10:
                - Supported `sample_rate`: 130
                - Supported `resolution`: 14

        Args:
            ecg_callback: A function to be called whenever new ECG data arrives.
            sample_rate: The desired sampling rate for the ECG stream.
            resolution: The data resolution setting.
        """
        self._ecg_callback = ecg_callback
        settings = MeasurementSettings(
            measurement_type=PmdMeasurementType.ECG,
            settings=[
                MeasurementSettings.SettingType(
                    type=PmdSettingType.SAMPLE_RATE, values=[sample_rate]
                ),
                MeasurementSettings.SettingType(
                    type=PmdSettingType.RESOLUTION, values=[resolution]
                ),
            ],
        )
        await self.start_stream(settings)

    async def stop_ecg_stream(self) -> None:
        """Stops the Electrocardiogram (ECG) data stream."""
        self._ecg_callback = None
        await self.stop_stream(PmdMeasurementType.ECG)

    async def start_acc_stream(
        self,
        acc_callback: ACCCallback,
        sample_rate: int,
        resolution: int,
        range: int,
        channels: int | None = None,
    ) -> None:
        """Starts the Accelerometer (ACC) data stream.

        Device Support:
            - Polar H10:
                - Supported `sample_rate`: 25, 50, 100, 200
                - Supported `resolution`: 16
                - Supported `range`: 2, 4, 8
                - Supported `channels`: Leave as None
            - Polar Verity Sense:
                - Supported `sample_rate`: 52
                - Supported `resolution`: 16
                - Supported `range`: 8
                - Supported `channels`: 3

        Args:
            acc_callback: A function to be called whenever new ACC data arrives.
            sample_rate: The desired sampling rate for the ACC stream.
            resolution: The data resolution setting.
            range: The measurement range of the accelerometer.
            channels: The number of channels to use. Defaults to None.
        """
        self._acc_callback = acc_callback

        setting_list = [
            MeasurementSettings.SettingType(
                type=PmdSettingType.SAMPLE_RATE, values=[sample_rate]
            ),
            MeasurementSettings.SettingType(
                type=PmdSettingType.RESOLUTION, values=[resolution]
            ),
            MeasurementSettings.SettingType(type=PmdSettingType.RANGE, values=[range]),
        ]
        if channels is not None:
            setting_list.append(
                MeasurementSettings.SettingType(
                    type=PmdSettingType.CHANNELS, values=[channels]
                )
            )

        settings = MeasurementSettings(
            measurement_type=PmdMeasurementType.ACC,
            settings=setting_list,
        )
        await self.start_stream(settings)

    async def stop_acc_stream(self) -> None:
        """Stops the Accelerometer (ACC) data stream."""
        self._acc_callback = None
        await self.stop_stream(PmdMeasurementType.ACC)

    async def start_ppi_stream(self, ppi_callback: PPICallback) -> None:
        """Starts the Peak-to-Peak Interval (PPI) data stream.

        Device Support:
            - Polar Verity Sense: No specific configuration is needed for PPI streams.

        Args:
            ppi_callback: A function to be called whenever new PPI data arrives.
        """
        self._ppi_callback = ppi_callback
        settings = MeasurementSettings(
            measurement_type=PmdMeasurementType.PPI, settings=[]
        )
        await self.start_stream(settings)

    async def stop_ppi_stream(self) -> None:
        """Stops the Peak-to-Peak Interval (PPI) data stream."""
        self._ppi_callback = None
        await self.stop_stream(PmdMeasurementType.PPI)

    async def start_ppg_stream(
        self,
        ppg_callback: PPGCallback,
        sample_rate: int,
        resolution: int,
        channels: int,
    ) -> None:
        """Starts the Photoplethysmography (PPG) data stream.

        Device Support:
            - Polar Verity Sense:
                - Supported `sample_rate`: 55
                - Supported `resolution`: 22
                - Supported `channels`: 4

        Args:
            ppg_callback: A function to be called whenever new PPG data arrives.
            sample_rate: The desired sampling rate for the PPG stream.
            resolution: The data resolution setting.
            channels: The number of optical channels to capture.
        """
        self._ppg_callback = ppg_callback
        settings = MeasurementSettings(
            measurement_type=PmdMeasurementType.PPG,
            settings=[
                MeasurementSettings.SettingType(
                    type=PmdSettingType.SAMPLE_RATE, values=[sample_rate]
                ),
                MeasurementSettings.SettingType(
                    type=PmdSettingType.RESOLUTION, values=[resolution]
                ),
                MeasurementSettings.SettingType(
                    type=PmdSettingType.CHANNELS, values=[channels]
                ),
            ],
        )
        await self.start_stream(settings)

    async def stop_ppg_stream(self) -> None:
        """Stops the Photoplethysmography (PPG) data stream."""
        self._ppg_callback = None
        await self.stop_stream(PmdMeasurementType.PPG)

    async def start_gyro_stream(
        self,
        gyro_callback: GyroCallback,
        sample_rate: int,
        resolution: int,
        range: int,
        channels: int,
    ) -> None:
        """Starts the Gyroscope (Gyro) data stream.

        Device Support:
            - Polar Verity Sense:
                - Supported `sample_rate`: 52
                - Supported `resolution`: 16
                - Supported `range`: 2000
                - Supported `channels`: 3

        Args:
            gyro_callback: A function to be called whenever new Gyro data arrives.
            sample_rate: The desired sampling rate for the Gyro stream.
            resolution: The data resolution setting.
            range: The measurement range of the gyroscope in deg/sec.
            channels: The number of channels to use.
        """
        self._gyro_callback = gyro_callback
        settings = MeasurementSettings(
            measurement_type=PmdMeasurementType.GYRO,
            settings=[
                MeasurementSettings.SettingType(
                    type=PmdSettingType.SAMPLE_RATE, values=[sample_rate]
                ),
                MeasurementSettings.SettingType(
                    type=PmdSettingType.RESOLUTION, values=[resolution]
                ),
                MeasurementSettings.SettingType(
                    type=PmdSettingType.RANGE, values=[range]
                ),
                MeasurementSettings.SettingType(
                    type=PmdSettingType.CHANNELS, values=[channels]
                ),
            ],
        )
        await self.start_stream(settings)

    async def stop_gyro_stream(self) -> None:
        """Stops the Gyroscope (Gyro) data stream."""
        self._gyro_callback = None
        await self.stop_stream(PmdMeasurementType.GYRO)

    async def start_mag_stream(
        self,
        mag_callback: MAGCallback,
        sample_rate: int,
        resolution: int,
        range: int,
        channels: int,
    ) -> None:
        """Starts the Magnetometer (MAG) data stream.

        Device Support:
            - Polar Verity Sense:
                - Supported `sample_rate`: 10, 20, 50, 100
                - Supported `resolution`: 16
                - Supported `range`: 50
                - Supported `channels`: 3

        Args:
            mag_callback: A function to be called whenever new MAG data arrives.
            sample_rate: The desired sampling rate for the MAG stream.
            resolution: The data resolution setting.
            range: The measurement range of the magnetometer.
            channels: The number of channels to use.
        """
        self._mag_callback = mag_callback
        settings = MeasurementSettings(
            measurement_type=PmdMeasurementType.MAG,
            settings=[
                MeasurementSettings.SettingType(
                    type=PmdSettingType.SAMPLE_RATE, values=[sample_rate]
                ),
                MeasurementSettings.SettingType(
                    type=PmdSettingType.RESOLUTION, values=[resolution]
                ),
                MeasurementSettings.SettingType(
                    type=PmdSettingType.RANGE, values=[range]
                ),
                MeasurementSettings.SettingType(
                    type=PmdSettingType.CHANNELS, values=[channels]
                ),
            ],
        )
        await self.start_stream(settings)

    async def stop_mag_stream(self) -> None:
        """Stops the Magnetometer (MAG) data stream."""
        self._mag_callback = None
        await self.stop_stream(PmdMeasurementType.MAG)

    async def start_hr_stream(self, hr_callback: HRCallback) -> None:
        """Starts the Heart Rate (HR) measurement stream.

        Unlike PMD streams, this subscribes to the standard Bluetooth Heart Rate profile.

        Args:
            hr_callback: A function to be called whenever new HR data arrives.
        """
        self._hr_callback = hr_callback
        await self._client.start_notify(
            PolarCharacteristic.HEART_RATE.value,
            self._handle_hr_measurement,
        )

    async def stop_hr_stream(self) -> None:
        """Stops the Heart Rate (HR) measurement stream."""
        self._hr_callback = None
        await self._client.stop_notify(PolarCharacteristic.HEART_RATE.value)

    def _handle_pmd_control(
        self, _: BleakGATTCharacteristic | int, data: bytearray
    ) -> None:
        """Queue PMD control point responses and their continuation packets.

        Responses start with 0xF0 (the response code); continuation packets of
        a multi-packet reply start with their "more" flag (0x00 or 0x01). On
        BlueZ, reading the PMD control point while notifications are enabled can
        also surface the feature packet as a notification; those start with
        0x0F and must not be mixed into the response queue.
        """
        if not data or data[0] not in (0xF0, 0x00, 0x01):
            return

        self._queue_pmd_control.put_nowait(data)

    def _handle_pmd_data(
        self, _: BleakGATTCharacteristic | int, data: bytearray
    ) -> None:
        """Parses raw PMD data and dispatches it to the appropriate registered callback."""
        self._pmd_counts["raw"] = self._pmd_counts.get("raw", 0) + 1
        try:
            parsed_data = parsers.parse_polar_data(data, self._factors.get)
        except (ValueError, IndexError, KeyError, struct.error) as exc:
            self._pmd_counts["errors"] = self._pmd_counts.get("errors", 0) + 1
            if self._pmd_event_cb is not None:
                self._pmd_event_cb(
                    f"PMD parse error: {type(exc).__name__}: {exc} "
                    f"(raw len={len(data)})",
                    "warning",
                )
            return  # Skip malformed frames

        if parsed_data is None:
            return

        if self._pmd_counts["raw"] % PMD_STATS_INTERVAL == 0 and self._pmd_event_cb:
            c = self._pmd_counts
            self._pmd_event_cb(
                f"PMD stats @ {c['raw']}: raw={c['raw']} ecg={c.get('ecg', 0)} "
                f"acc={c.get('acc', 0)} ppg={c.get('ppg', 0)} ppi={c.get('ppi', 0)} "
                f"gyro={c.get('gyro', 0)} mag={c.get('mag', 0)} "
                f"err={c.get('errors', 0)}",
                "info",
            )
        try:
            match parsed_data:
                case ECGData() if self._ecg_callback:
                    self._ecg_callback(parsed_data)
                case ACCData() if self._acc_callback:
                    self._acc_callback(parsed_data)
                case PPIData() if self._ppi_callback:
                    self._ppi_callback(parsed_data)
                case PPGData() if self._ppg_callback:
                    self._ppg_callback(parsed_data)
                case GyroData() if self._gyro_callback:
                    self._gyro_callback(parsed_data)
                case MAGData() if self._mag_callback:
                    self._mag_callback(parsed_data)
                case _:
                    return
            kind = type(parsed_data).__name__.removesuffix("Data").lower()
            self._pmd_counts[kind] = self._pmd_counts.get(kind, 0) + 1
        except Exception as cb_exc:
            if self._pmd_event_cb:
                self._pmd_event_cb(f"PMD callback error: {cb_exc}", "error")

    def _handle_hr_measurement(
        self, _: BleakGATTCharacteristic | int, data: bytearray
    ) -> None:
        """Parses raw heart rate data and dispatches it to the registered callback."""
        try:
            parsed_data = parsers.parse_hr_data(data)
        except (ValueError, IndexError):
            return  # Skip malformed HR frames
        if self._hr_callback:
            self._hr_callback(parsed_data)
