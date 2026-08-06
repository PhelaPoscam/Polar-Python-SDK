"""Heart rate data parsing functions.

Implements the Bluetooth GATT Heart Rate Measurement characteristic (UUID 0x2A37).

Flags byte (data[0]):
    Bit 0 (0x01): Heart rate format — 0 = uint8, 1 = uint16
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
    rr_present = (flags & 0x10) != 0

    if hr_is_16bit:
        if len(data) < 3:
            raise ValueError("16-bit HR but data too short for HR value")
        heartrate = int.from_bytes(data[1:3], byteorder="little", signed=False)
        rr_start = 3
    else:
        heartrate = data[1]
        rr_start = 2

    rr_intervals: list[float] = []
    if rr_present:
        for i in range(rr_start, len(data) - 1, 2):
            rr_raw = int.from_bytes(data[i : i + 2], byteorder="little", signed=False)
            rr_intervals.append(rr_raw / 1024.0 * 1000.0)

    return HRData(heartrate=heartrate, rr_intervals=rr_intervals)
