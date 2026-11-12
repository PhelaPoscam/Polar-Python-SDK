"""Battery service polling and level reading for Polar devices."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

BATTERY_SERVICE_UUID = "00002a19-0000-1000-8000-00805f9b34fb"


async def read_battery(conn: Any) -> str:
    """Read the battery percentage from a connected Polar device."""
    if not conn or not getattr(conn, "polar_device", None):
        return "-"
    client = getattr(conn.polar_device, "_client", None)
    if not client or not getattr(client, "is_connected", False):
        return "-"

    try:
        data = await client.read_gatt_char(BATTERY_SERVICE_UUID)
        return f"{int(data[0])}%" if data else "-"
    except Exception as e:
        logger.debug("Failed to read battery characteristic: %s", e)
        return "-"


async def update_battery_loop(
    conn: Any,
    state: dict[str, Any],
    interval_s: float = 30.0,
) -> None:
    """Background task: periodically refresh the battery level in state."""
    while True:
        state["battery"] = await read_battery(conn)
        await asyncio.sleep(interval_s)
