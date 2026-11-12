"""Heart rate data parsing functions.

Implements the Bluetooth GATT Heart Rate Measurement characteristic (UUID 0x2A37).

Flags byte (data[0]):
    Bit 0 (0x01): Heart rate format — 0 = uint8, 1 = uint16
    Bit 1 (0x02): Sensor contact detected — 0 = no contact, 1 = contact detected (when supported)
    Bit 2 (0x04): Sensor contact feature supported — 0 = not supported, 1 = supported
    Bit 3 (0x08): Energy Expended field present — 0 = no, 1 = yes
    Bit 4 (0x10): RR interval present — 0 = no, 1 = yes

RR intervals are uint16 in 1/1024-second units, converted to ms on output.
"""

from ..models import HRData


def parse_hr_data(data: bytearray) -> HRData:
    """Parse heart rate data per Bluetooth SIG GATT 0x2A37."""
    if len(data) < 2:
        raise ValueError("Heart rate data too short")

    flags = data[0]
    hr_is_16bit = (flags & 0x01) != 0
    contact_supported = (flags & 0x04) != 0
    contact_detected = bool(flags & 0x02) if contact_supported else None
    energy_expended = (flags & 0x08) != 0
    rr_present = (flags & 0x10) != 0

    if hr_is_16bit:
        if len(data) < 3:
            raise ValueError("16-bit HR but data too short for HR value")
        heartrate = int.from_bytes(data[1:3], byteorder="little", signed=False)
        offset = 3
    else:
        heartrate = data[1]
        offset = 2

    if energy_expended:
        offset += 2  # Energy Expended field is uint16

    rr_intervals: list[float] = []
    if rr_present:
        for i in range(offset, len(data) - 1, 2):
            rr_raw = int.from_bytes(data[i : i + 2], byteorder="little", signed=False)
            rr_intervals.append(rr_raw / 1024.0 * 1000.0)

    return HRData(
        heartrate=heartrate,
        rr_intervals=rr_intervals,
        contact_detected=contact_detected,
    )
