"""BLE discovery: a MAC target must come back with its name when one is advertised."""

from types import SimpleNamespace

import pytest

from polar_ble_sdk.connector import ble_discovery

H10_MAC = "A0:9E:1A:EA:39:62"


def fake_scanner(adverts):
    """BleakScanner stand-in that replays (device, advertisement) pairs on start."""

    class FakeScanner:
        def __init__(self, callback):
            self._callback = callback

        async def start(self):
            for device, adv in adverts:
                self._callback(device, adv)

        async def stop(self):
            pass

    return FakeScanner


@pytest.mark.asyncio
async def test_mac_target_waits_for_the_named_advertisement(monkeypatch) -> None:
    nameless = SimpleNamespace(address=H10_MAC, name=None)
    named = SimpleNamespace(address=H10_MAC, name="Polar H10 EA396220")
    no_name = SimpleNamespace(local_name=None)
    monkeypatch.setattr(
        ble_discovery,
        "BleakScanner",
        fake_scanner([(nameless, no_name), (named, no_name)]),
    )
    device = await ble_discovery.discover_polar_device(H10_MAC, timeout=1.0)
    assert device is named  # the H10 connector is chosen from this name


@pytest.mark.asyncio
async def test_nameless_match_is_still_returned_at_timeout(monkeypatch) -> None:
    nameless = SimpleNamespace(address=H10_MAC, name=None)
    monkeypatch.setattr(
        ble_discovery,
        "BleakScanner",
        fake_scanner([(nameless, SimpleNamespace(local_name=None))]),
    )
    device = await ble_discovery.discover_polar_device(H10_MAC, timeout=0.3)
    assert device is nameless
