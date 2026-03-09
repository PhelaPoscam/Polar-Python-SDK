#!/usr/bin/env python3
"""Unified Nuanic diagnostics CLI.

This script consolidates exploratory reverse-engineering tools into one entrypoint:
- Service/characteristic discovery
- Notify packet profiling (size and rate)
- Optional write-probe on config characteristics
- Optional buffer inspection
"""

import argparse
import asyncio
import struct
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from awe_polar.nuanic_ring.connector import NuanicConnector

SERVICE_UUID = "5491faaf-b0c2-4167-8f3d-bc6b31db69e7"
BUFFER_CHAR = "7c3b82e7-22b7-4cb6-8458-ba325edf6ede"
MYSTERY_NOTIFY = "42dcb71b-1817-43bd-8ea3-7272780a1c9f"

WRITE_ONLY_CHARS = {
    "2175c13f-60e4-4de5-80af-0d06f1b54880": "WRITE_1",
}

WRITE_READ_CHARS = {
    "516b0fb6-d861-4619-9dd0-0105e8b85128": "CONFIG_1",
    "dc9c31a7-fbd3-467a-8777-10900c423d3b": "CONFIG_2",
    "3cce21a7-e602-4e02-8c52-1e0366c1c846": "CONFIG_3",
}

WRITE_PATTERNS = {
    "enable_1": b"\x01",
    "enable_1_0": b"\x01\x00",
    "enable_2": b"\x02",
    "enable_all": b"\xff",
    "mode_3": b"\x03",
    "stream_1_1": b"\x01\x01",
    "extended_4": b"\x04",
    "reset_0": b"\x00",
}


class NotifyStats:
    def __init__(self):
        self.count = 0
        self.first_ts = None
        self.last_ts = None
        self.size_dist = defaultdict(int)
        self.first_packet = None
        self.last_packet = None

    def add(self, data: bytes):
        now = time.time()
        self.count += 1
        if self.first_ts is None:
            self.first_ts = now
            self.first_packet = data
        self.last_ts = now
        self.last_packet = data
        self.size_dist[len(data)] += 1

    def freq_hz(self) -> float:
        if not self.first_ts or not self.last_ts or self.last_ts <= self.first_ts:
            return 0.0
        return self.count / (self.last_ts - self.first_ts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Nuanic diagnostics: discover, profile notify streams, write-probe, and inspect buffer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --ring-addr 56:C2:72:F2:07:04
  %(prog)s --ring-addr 56:C2:72:F2:07:04 --profile-seconds 20
  %(prog)s --ring-addr 56:C2:72:F2:07:04 --write-probe --buffer-poll 5
  %(prog)s --ring-addr 56:C2:72:F2:07:04 --no-profile --buffer-only
""",
    )
    parser.add_argument(
        "legacy_ring_addr",
        nargs="?",
        help="Optional BLE address (legacy positional argument).",
    )
    parser.add_argument(
        "--ring-addr",
        default=None,
        help="BLE address of ring. If omitted, connector selection is used.",
    )
    parser.add_argument(
        "--profile-seconds",
        type=int,
        default=15,
        help="Duration for notify profiling (default: 15).",
    )
    parser.add_argument(
        "--no-profile",
        action="store_true",
        help="Skip notify profiling.",
    )
    parser.add_argument(
        "--write-probe",
        action="store_true",
        help="Run write probes against known config characteristics.",
    )
    parser.add_argument(
        "--buffer-poll",
        type=int,
        default=1,
        help="Read buffer characteristic N times (default: 1).",
    )
    parser.add_argument(
        "--buffer-interval",
        type=float,
        default=2.0,
        help="Seconds between buffer reads when --buffer-poll > 1 (default: 2.0).",
    )
    parser.add_argument(
        "--buffer-only",
        action="store_true",
        help="Only inspect buffer (skip discovery and profile).",
    )
    return parser.parse_args()


def pick_ring_addr(args: argparse.Namespace) -> Optional[str]:
    return args.ring_addr or args.legacy_ring_addr


def print_header(title: str):
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def iter_service_chars(client):
    for service in client.services:
        if service.uuid.lower() == SERVICE_UUID.lower():
            for char in service.characteristics:
                yield char


def summarize_i16(packet: bytes) -> str:
    if len(packet) < 2:
        return "n/a"
    vals = []
    for i in range(0, len(packet) - 1, 2):
        vals.append(struct.unpack("<h", packet[i : i + 2])[0])
    if not vals:
        return "n/a"
    return f"min={min(vals)}, max={max(vals)}, avg={sum(vals)/len(vals):.1f}, count={len(vals)}"


async def discover_chars(client):
    print_header("STEP 1: DISCOVERY")
    chars = list(iter_service_chars(client))
    print(f"Service: {SERVICE_UUID}")
    print(f"Characteristics: {len(chars)}\n")
    for idx, char in enumerate(chars, 1):
        props = ", ".join(char.properties)
        print(f"[{idx:2d}] {char.uuid}")
        print(f"     Properties: {props}")
    return chars


async def read_non_notify(client, chars):
    print_header("STEP 2: READ SNAPSHOT")
    for char in chars:
        props = set(char.properties)
        if "read" in props and "notify" not in props:
            try:
                value = await client.read_gatt_char(char.uuid)
                preview = bytes(value).hex()[:64]
                print(f"[READ] {char.uuid} | {len(value)} bytes | {preview}...")
            except Exception as exc:
                print(f"[READ] {char.uuid} | FAILED: {exc}")


async def profile_notify(client, chars, seconds: int):
    print_header("STEP 3: NOTIFY PROFILE")
    stats: Dict[str, NotifyStats] = {}
    notify_chars = [c for c in chars if "notify" in c.properties]

    for char in notify_chars:
        key = char.uuid.lower()
        stats[key] = NotifyStats()

        def make_cb(k):
            def cb(_sender, data):
                stats[k].add(bytes(data))

            return cb

        await client.start_notify(char.uuid, make_cb(key))
        print(f"[SUB] {char.uuid}")

    print(f"\nListening for {seconds}s... move/interact with the ring.\n")
    await asyncio.sleep(max(1, seconds))

    for char in notify_chars:
        try:
            await client.stop_notify(char.uuid)
        except Exception:
            pass

    print_header("STEP 4: PROFILE RESULTS")
    for char in notify_chars:
        key = char.uuid.lower()
        st = stats[key]
        print(f"[NOTIFY] {char.uuid}")
        print(f"  packets: {st.count}")
        print(f"  rate: {st.freq_hz():.2f} Hz")
        print(f"  sizes: {dict(sorted(st.size_dist.items())) if st.size_dist else {}}")
        if st.first_packet is not None:
            print(f"  first: {st.first_packet.hex()[:64]}...")
            print(f"  last:  {st.last_packet.hex()[:64]}...")
            print(f"  int16 summary: {summarize_i16(st.first_packet)}")
        if key == MYSTERY_NOTIFY.lower() and st.count == 0:
            print("  note: mystery notify remained silent in this run")


async def run_write_probe(client):
    print_header("STEP 5: WRITE PROBE")
    for name, payload in WRITE_PATTERNS.items():
        print(f"\n[CMD] {name}: {payload.hex()}")
        for uuid, label in WRITE_READ_CHARS.items():
            try:
                await client.write_gatt_char(uuid, payload)
                try:
                    echoed = await client.read_gatt_char(uuid)
                    print(
                        f"  [OK] {label} ({uuid[:8]}...) echo={bytes(echoed).hex()[:32]}"
                    )
                except Exception:
                    print(f"  [OK] {label} ({uuid[:8]}...) write only in this session")
            except Exception as exc:
                print(f"  [FAIL] {label} ({uuid[:8]}...): {exc}")

        for uuid, label in WRITE_ONLY_CHARS.items():
            try:
                await client.write_gatt_char(uuid, payload)
                print(f"  [OK] {label} ({uuid[:8]}...)")
            except Exception as exc:
                print(f"  [FAIL] {label} ({uuid[:8]}...): {exc}")


async def inspect_buffer(client, polls: int, interval: float):
    print_header("STEP 6: BUFFER INSPECTION")
    previous = None
    for idx in range(max(1, polls)):
        try:
            data = bytes(await client.read_gatt_char(BUFFER_CHAR))
            changed = previous is not None and previous != data
            print(
                f"[BUF {idx+1}] {len(data)} bytes | changed={changed} | first32={data.hex()[:64]}..."
            )
            if len(data) >= 2:
                print(
                    f"         int16 summary: {summarize_i16(data[: min(len(data), 120)])}"
                )
            previous = data
        except Exception as exc:
            print(f"[BUF {idx+1}] FAILED: {exc}")

        if idx < polls - 1:
            await asyncio.sleep(max(0.1, interval))


async def main() -> int:
    args = parse_args()
    ring_addr = pick_ring_addr(args)

    connector = NuanicConnector(target_address=ring_addr)
    if not await connector.connect():
        print("[FAIL] Could not connect to ring")
        return 1

    print(f"\n[INIT] Connected to: {connector.target_address or 'selected ring'}")

    try:
        client = connector.client
        chars = list(iter_service_chars(client))
        if not chars:
            print(f"[FAIL] Service {SERVICE_UUID} not found")
            return 1

        if args.buffer_only:
            await inspect_buffer(
                client, polls=args.buffer_poll, interval=args.buffer_interval
            )
            return 0

        discovered = await discover_chars(client)
        await read_non_notify(client, discovered)

        if not args.no_profile:
            await profile_notify(client, discovered, seconds=args.profile_seconds)

        if args.write_probe:
            await run_write_probe(client)

        if args.buffer_poll > 0:
            await inspect_buffer(
                client, polls=args.buffer_poll, interval=args.buffer_interval
            )

        return 0
    finally:
        await connector.disconnect()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n[STOP] Interrupted by user")
        raise SystemExit(1)
