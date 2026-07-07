"""BLE discovery helpers for Polar sensors."""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from bleak import BleakScanner

PREFERRED_POLAR_TOKENS = ("sense", "verity", "oh1", "h10")


def _device_name(device, advertisement_data=None) -> str:
    name = getattr(device, "name", None)
    if not name and advertisement_data is not None:
        name = getattr(advertisement_data, "local_name", None)
    return name or ""


def _device_matches_target(device, name: str, target: Optional[str]) -> bool:
    if not target:
        return False

    target_lower = target.lower()
    address = (getattr(device, "address", "") or "").lower()
    return target_lower in name.lower() or target_lower == address


def _is_polar_name(name: str) -> bool:
    return "polar" in name.lower()


def _is_preferred_polar_name(name: str) -> bool:
    name_lower = name.lower()
    return _is_polar_name(name) and any(
        token in name_lower for token in PREFERRED_POLAR_TOKENS
    )


async def discover_polar_device(
    target: Optional[str] = None,
    *,
    timeout: float = 20.0,
    fallback_after: float = 6.0,
):
    """Find a Polar BLE device, returning early for exact/preferred sensor matches."""
    fallback_device = None
    selected_device = None
    selected_event = asyncio.Event()
    start_time = time.monotonic()

    def _on_detect(device, advertisement_data):
        nonlocal fallback_device, selected_device

        name = _device_name(device, advertisement_data)
        if _device_matches_target(device, name, target):
            selected_device = device
            selected_event.set()
            return

        if target or not _is_polar_name(name):
            return

        if fallback_device is None:
            fallback_device = device

        if _is_preferred_polar_name(name):
            selected_device = device
            selected_event.set()

    scanner = BleakScanner(_on_detect)
    await scanner.start()
    try:
        while time.monotonic() - start_time < timeout:
            if selected_event.is_set():
                return selected_device
            if fallback_device and time.monotonic() - start_time >= fallback_after:
                return fallback_device
            await asyncio.sleep(0.1)
    finally:
        await scanner.stop()

    return selected_device or fallback_device


async def discover_dual_polar_devices(
    h10_target: Optional[str] = None,
    sense_target: Optional[str] = None,
    *,
    timeout: float = 10.0,
) -> tuple[Optional[object], Optional[object]]:
    """Scan for both a Polar H10 and a Polar Verity Sense/OH1 simultaneously.

    Returns:
        tuple: (h10_device, sense_device)
    """
    found_h10 = None
    found_sense = None

    def _on_detect(device, advertisement_data):
        nonlocal found_h10, found_sense
        name = _device_name(device, advertisement_data)
        name_lower = name.lower()

        # Match H10
        is_h10_candidate = "h10" in name_lower
        if h10_target:
            target_l = h10_target.lower()
            is_h10_candidate = (
                target_l in name_lower or target_l == device.address.lower()
            )

        if is_h10_candidate and not found_h10:
            found_h10 = device

        # Match Sense / Verity / OH1
        is_sense_candidate = any(
            token in name_lower for token in ("sense", "verity", "oh1")
        )
        if sense_target:
            target_l = sense_target.lower()
            is_sense_candidate = (
                target_l in name_lower or target_l == device.address.lower()
            )

        if is_sense_candidate and not found_sense:
            found_sense = device

    scanner = BleakScanner(_on_detect)
    await scanner.start()
    try:
        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout:
            if found_h10 and found_sense:
                break
            await asyncio.sleep(0.1)
    finally:
        await scanner.stop()

    return found_h10, found_sense
