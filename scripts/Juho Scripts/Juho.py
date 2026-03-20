#!/usr/bin/env python3

import asyncio
import csv
import struct
import sys
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional
import tkinter as tk
from bleak import BleakClient, BleakScanner

TARGET_NAME = "Nuanic"
SCAN_SECONDS = 12
CONNECT_TIMEOUT = 15.0
PAIR_BEFORE_GATT = True
READ_POLL_SECONDS = 2.0

SERVICE_UUID = "5491faaf-b0c2-4167-8f3d-bc6b31db69e7"
STATE_UUID = "3c180fcc-bfec-4b7c-8e52-1a37f123e449"
STORAGE_UUID = "7c3b82e7-22b7-4cb6-8458-ba325edf6ede"
LIVE_EDA_UUID = "42dcb71b-1817-43bd-8ea3-7272780a1c9f"
LIVE_DNA_UUID = "d306262b-c8c9-4c4b-9050-3a41dea706e5"
SET_TIME_UUID = "dc9c31a7-fbd3-467a-8777-10900c423d3b"
SAMPLE_RATE_UUID = "516b0fb6-d861-4619-9dd0-0105e8b85128"
STORAGE_FORMAT_UUID = "3cce21a7-e602-4e02-8c52-1e0366c1c846"
BATTERY_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

STATE_TEXT = {
    0: "Initializing",
    1: "Off finger / stopped",
    2: "On finger / tracking",
    3: "Docked",
}

LIVE_DNA_GRAPH_TITLES = [
    "LIVE_DNA word0 (timestamp)",
    "LIVE_DNA word1 (?)",
    "LIVE_DNA word2 (live EDA)",
    "LIVE_DNA word3 (composite score / value?)",
]

PROGRAM_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROGRAM_DIR / "live_dna_logs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CSV_HEADER = [
    "pc_time",
    "packet_source",
    "packet_via",
    "word0_clock_candidate",
    "word1_session_candidate",
    "word2_signal_candidate",
    "word3_quality_candidate",
]

TARGETS = [
    {"label": "STATE", "uuid": STATE_UUID, "decode_mode": "state"},
    {"label": "STORAGE", "uuid": STORAGE_UUID, "decode_mode": "bytes"},
    {"label": "LIVE_EDA", "uuid": LIVE_EDA_UUID, "decode_mode": "live_eda"},
    {"label": "LIVE_DNA", "uuid": LIVE_DNA_UUID, "decode_mode": "live_dna"},
    {"label": "SET_TIME", "uuid": SET_TIME_UUID, "decode_mode": "bytes"},
    {"label": "SAMPLE_RATE", "uuid": SAMPLE_RATE_UUID, "decode_mode": "bytes"},
    {"label": "STORAGE_FORMAT", "uuid": STORAGE_FORMAT_UUID, "decode_mode": "bytes"},
    {"label": "BATTERY", "uuid": BATTERY_UUID, "decode_mode": "battery"},
]


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def normalize_uuid(value: str) -> str:
    return value.strip().lower()


def bytes_to_int_list(data: bytearray) -> List[int]:
    return [int(b) & 0xFF for b in data]


def state_to_text(value: Optional[int]) -> str:
    if value is None:
        return "EMPTY"
    return STATE_TEXT.get(value, f"Unknown({value})")


def print_header(label: str, uuid: str, via: str) -> None:
    print("\n" + "=" * 100)
    print(f"CHARACTERISTIC: {label} | via={via} | uuid={uuid}")
    print(f"time: {now_str()}")


class LiveDNACSVLogger:
    def __init__(self) -> None:
        session_name = datetime.now().strftime("live_dna_%Y%m%d_%H%M%S.csv")
        self.csv_path = OUTPUT_DIR / session_name
        self._lock = threading.Lock()
        with self.csv_path.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.writer(file_handle)
            writer.writerow(CSV_HEADER)
        print(f"[LIVE_DNA-CSV] logging to: {self.csv_path}")

    def append_row(
        self,
        packet_time: str,
        packet_via: str,
        word0: int,
        word1: int,
        word2: int,
        word3: int,
    ) -> None:
        with self._lock:
            with self.csv_path.open("a", newline="", encoding="utf-8") as file_handle:
                writer = csv.writer(file_handle)
                writer.writerow(
                    [
                        packet_time,
                        LIVE_DNA_UUID,
                        packet_via,
                        word0,
                        word1,
                        word2,
                        word3,
                    ]
                )


class DataWindow:
    HISTORY_LEN = 240

    def __init__(self) -> None:
        self.root: Optional[tk.Tk] = None
        self.value_labels: Dict[str, tk.Label] = {}
        self.graph_window: Optional[tk.Toplevel] = None
        self.graph_canvases: Dict[str, tk.Canvas] = {}
        self.graph_stats: Dict[str, tk.Label] = {}
        self.graph_last_packet: Optional[tk.Label] = None

        self.series: Dict[str, Deque[float]] = {
            "live_eda_ohm": deque(maxlen=self.HISTORY_LEN),
            "live_dna_word0": deque(maxlen=self.HISTORY_LEN),
            "live_dna_word1": deque(maxlen=self.HISTORY_LEN),
            "live_dna_word2": deque(maxlen=self.HISTORY_LEN),
            "live_dna_word3": deque(maxlen=self.HISTORY_LEN),
        }

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self.root = tk.Tk()
        self.root.title("Data")
        self.root.geometry("1550x900")
        self.root.minsize(1300, 760)

        outer = tk.Frame(self.root, padx=8, pady=8)
        outer.pack(fill="both", expand=True)

        fields = [
            "time",
            "device_name",
            "device_address",
            "connect_status",
            "service_found",
            "last_packet_source",
            "last_status",
            "state_found",
            "state_props",
            "state_read_status",
            "state_notify_status",
            "state_raw_bytes",
            "state_value",
            "state_text",
            "storage_found",
            "storage_props",
            "storage_read_status",
            "storage_notify_status",
            "storage_raw_bytes",
            "live_eda_found",
            "live_eda_props",
            "live_eda_read_status",
            "live_eda_notify_status",
            "live_eda_raw_bytes",
            "live_eda_packet_len",
            "live_eda_boot_count",
            "live_eda_timestamp_ms",
            "live_eda_ohm",
            "live_eda_kohm",
            "live_eda_mohm",
            "live_dna_found",
            "live_dna_props",
            "live_dna_read_status",
            "live_dna_notify_status",
            "live_dna_raw_bytes",
            "live_dna_word0",
            "live_dna_word1",
            "live_dna_word2",
            "live_dna_word3",
            "set_time_found",
            "set_time_props",
            "set_time_read_status",
            "set_time_notify_status",
            "set_time_raw_bytes",
            "sample_rate_found",
            "sample_rate_props",
            "sample_rate_read_status",
            "sample_rate_notify_status",
            "sample_rate_raw_bytes",
            "storage_format_found",
            "storage_format_props",
            "storage_format_read_status",
            "storage_format_notify_status",
            "storage_format_raw_bytes",
            "battery_found",
            "battery_props",
            "battery_read_status",
            "battery_notify_status",
            "battery_raw_bytes",
            "battery_level_percent",
        ]

        pair_columns = 4
        for index, field in enumerate(fields):
            row = index // pair_columns
            pair_col = index % pair_columns
            col = pair_col * 2

            name_label = tk.Label(
                outer,
                text=field,
                anchor="nw",
                justify="left",
                width=24,
                height=2,
                wraplength=180,
                font=("Courier", 10, "bold"),
            )
            name_label.grid(row=row, column=col, sticky="nw", padx=(0, 3), pady=(0, 2))

            value_label = tk.Label(
                outer,
                text="",
                anchor="nw",
                justify="left",
                width=24,
                height=2,
                wraplength=220,
                font=("Courier", 10),
            )
            value_label.grid(
                row=row, column=col + 1, sticky="nw", padx=(0, 8), pady=(0, 2)
            )

            self.value_labels[field] = value_label

        self._create_graph_window()
        self.root.mainloop()

    def _create_graph_window(self) -> None:
        if self.root is None:
            return

        self.graph_window = tk.Toplevel(self.root)
        self.graph_window.title("Graphs")
        self.graph_window.geometry("1200x860")
        self.graph_window.minsize(980, 700)
        self.graph_window.protocol("WM_DELETE_WINDOW", self.graph_window.withdraw)

        top = tk.Frame(self.graph_window, padx=8, pady=8)
        top.pack(fill="both", expand=True)

        self.graph_last_packet = tk.Label(
            top,
            text="last plotted packet: none yet",
            anchor="w",
            justify="left",
            font=("Courier", 11, "bold"),
        )
        self.graph_last_packet.pack(fill="x", pady=(0, 6))

        grid = tk.Frame(top)
        grid.pack(fill="both", expand=True)

        plot_keys = [
            ("live_eda_ohm", "LIVE_EDA ohm"),
            ("live_dna_word0", LIVE_DNA_GRAPH_TITLES[0]),
            ("live_dna_word1", LIVE_DNA_GRAPH_TITLES[1]),
            ("live_dna_word2", LIVE_DNA_GRAPH_TITLES[2]),
            ("live_dna_word3", LIVE_DNA_GRAPH_TITLES[3]),
        ]

        for row in range(3):
            grid.grid_rowconfigure(row, weight=1)
        for col in range(2):
            grid.grid_columnconfigure(col, weight=1)

        for index, (key, title) in enumerate(plot_keys):
            row = index // 2
            col = index % 2

            frame = tk.LabelFrame(
                grid,
                text=title,
                padx=6,
                pady=6,
                font=("Courier", 10, "bold"),
            )
            frame.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)

            canvas = tk.Canvas(
                frame,
                bg="white",
                highlightthickness=1,
                highlightbackground="black",
                width=520,
                height=220,
            )
            canvas.pack(fill="both", expand=True)

            stats = tk.Label(
                frame,
                text="waiting for data",
                anchor="w",
                justify="left",
                font=("Courier", 10),
            )
            stats.pack(fill="x", pady=(4, 0))

            self.graph_canvases[key] = canvas
            self.graph_stats[key] = stats

            canvas.bind(
                "<Configure>", lambda _event, graph_key=key: self._redraw_one(graph_key)
            )

    def update_values(self, updates: Dict[str, Any]) -> None:
        if self.root is None:
            return

        def apply() -> None:
            for key, value in updates.items():
                label = self.value_labels.get(key)
                if label is not None:
                    label.config(text=str(value))

        self.root.after(0, apply)

    def push_live_eda(self, packet_time: str, ohm_value: Optional[float]) -> None:
        if self.root is None or ohm_value is None:
            return

        def apply() -> None:
            if self.graph_last_packet is not None:
                self.graph_last_packet.config(
                    text=f"last plotted packet: {packet_time} (LIVE_EDA)"
                )
            self.series["live_eda_ohm"].append(float(ohm_value))
            self._redraw_one("live_eda_ohm")

        self.root.after(0, apply)

    def push_live_dna(self, packet_time: str, values: List[int]) -> None:
        if self.root is None:
            return

        def apply() -> None:
            if self.graph_last_packet is not None:
                self.graph_last_packet.config(
                    text=f"last plotted packet: {packet_time} (LIVE_DNA)"
                )
            keys = [
                "live_dna_word0",
                "live_dna_word1",
                "live_dna_word2",
                "live_dna_word3",
            ]
            for key, value in zip(keys, values[:4]):
                self.series[key].append(float(value))
                self._redraw_one(key)

        self.root.after(0, apply)

    def _redraw_one(self, key: str) -> None:
        canvas = self.graph_canvases.get(key)
        stats_label = self.graph_stats.get(key)
        if canvas is None or stats_label is None:
            return

        series = list(self.series[key])
        stats = self._draw_plot(canvas, series)
        if stats["count"] == 0:
            stats_label.config(text="waiting for data")
        else:
            stats_label.config(
                text=(
                    f"current={stats['current']}    "
                    f"min={stats['minimum']}    "
                    f"max={stats['maximum']}    "
                    f"points={stats['count']}"
                )
            )

    def _draw_plot(self, canvas: tk.Canvas, series: List[float]) -> Dict[str, Any]:
        canvas.delete("all")

        width = max(canvas.winfo_width(), 520)
        height = max(canvas.winfo_height(), 220)

        left = 60
        right = 16
        top = 16
        bottom = 32

        plot_width = max(10, width - left - right)
        plot_height = max(10, height - top - bottom)

        canvas.create_rectangle(
            left, top, left + plot_width, top + plot_height, outline="black"
        )

        if not series:
            canvas.create_text(
                left + plot_width / 2,
                top + plot_height / 2,
                text="No packets yet",
                font=("Courier", 12),
            )
            return {"count": 0, "current": None, "minimum": None, "maximum": None}

        y_min = min(series)
        y_max = max(series)
        if y_min == y_max:
            padding = max(1.0, abs(float(y_min)) * 0.02, 1.0)
            y_min -= padding
            y_max += padding

        def x_of(index: int) -> float:
            if len(series) <= 1:
                return left + plot_width / 2
            return left + (index / (len(series) - 1)) * plot_width

        def y_of(value: float) -> float:
            ratio = (value - y_min) / (y_max - y_min)
            return top + plot_height - ratio * plot_height

        mid = (y_min + y_max) / 2.0
        canvas.create_line(left, y_of(mid), left + plot_width, y_of(mid), dash=(4, 2))

        points: List[float] = []
        for index, value in enumerate(series):
            points.extend([x_of(index), y_of(value)])

        if len(points) >= 4:
            canvas.create_line(points, width=2)
        else:
            x = x_of(0)
            y = y_of(series[0])
            canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill="black")

        last_x = x_of(len(series) - 1)
        last_y = y_of(series[-1])
        canvas.create_oval(
            last_x - 3, last_y - 3, last_x + 3, last_y + 3, fill="red", outline="red"
        )
        canvas.create_text(
            left - 4, top, text=f"{y_max:.3f}", anchor="ne", font=("Courier", 9)
        )
        canvas.create_text(
            left - 4, y_of(mid), text=f"{mid:.3f}", anchor="e", font=("Courier", 9)
        )
        canvas.create_text(
            left - 4,
            top + plot_height,
            text=f"{y_min:.3f}",
            anchor="ne",
            font=("Courier", 9),
        )
        canvas.create_text(
            left, top + plot_height + 8, text="oldest", anchor="nw", font=("Courier", 9)
        )
        canvas.create_text(
            left + plot_width,
            top + plot_height + 8,
            text="newest",
            anchor="ne",
            font=("Courier", 9),
        )

        return {
            "count": len(series),
            "current": series[-1],
            "minimum": min(series),
            "maximum": max(series),
        }


LIVE_DNA_LOGGER = LiveDNACSVLogger()
GUI = DataWindow()


def find_characteristic_info(
    client: BleakClient, target_uuid: str
) -> Optional[Dict[str, Any]]:
    target_uuid = normalize_uuid(target_uuid)
    for service in client.services:
        for char in service.characteristics:
            if normalize_uuid(char.uuid) == target_uuid:
                return {
                    "service_uuid": service.uuid,
                    "char_uuid": char.uuid,
                    "description": char.description,
                    "properties": list(char.properties),
                }
    return None


def target_prefix(label: str) -> str:
    return label.lower()


def print_state_packet(raw: List[int], uuid: str, via: str) -> Dict[str, Any]:
    value = raw[0] if raw else None
    text = state_to_text(value)

    print_header("STATE", uuid, via)
    print(f"raw_bytes: {raw}")
    print(f"state_value: {value}")
    print(f"state_text: {text}")
    sys.stdout.flush()

    return {
        "time": now_str(),
        "state_raw_bytes": raw,
        "state_value": value,
        "state_text": text,
    }


def print_live_eda_packet(
    raw: List[int], data: bytearray, uuid: str, via: str
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "time": now_str(),
        "live_eda_raw_bytes": raw,
        "live_eda_packet_len": len(raw),
        "live_eda_boot_count": "",
        "live_eda_timestamp_ms": "",
        "live_eda_ohm": "",
        "live_eda_kohm": "",
        "live_eda_mohm": "",
    }

    print_header("LIVE_EDA", uuid, via)
    print(f"raw_bytes: {raw}")
    print(f"packet_len: {len(raw)}")

    if len(raw) == 14:
        boot_count, timestamp_ms, eda_ohm = struct.unpack("<HQI", bytes(data))
        eda_kohm = eda_ohm / 1000.0
        eda_mohm = eda_ohm / 1_000_000.0

        print(f"boot_count: {boot_count}")
        print(f"timestamp_ms: {timestamp_ms}")
        print(f"eda_ohm: {eda_ohm}")
        print(f"eda_kohm: {eda_kohm:.3f}")
        print(f"eda_mohm: {eda_mohm:.6f}")

        result.update(
            {
                "live_eda_boot_count": boot_count,
                "live_eda_timestamp_ms": timestamp_ms,
                "live_eda_ohm": eda_ohm,
                "live_eda_kohm": f"{eda_kohm:.3f}",
                "live_eda_mohm": f"{eda_mohm:.6f}",
                "_graph_live_eda_ohm": float(eda_ohm),
            }
        )
    else:
        print("decode_note: packet length is not 14, left undecoded")

    sys.stdout.flush()
    return result


def print_live_dna_packet(
    raw: List[int], data: bytearray, uuid: str, via: str
) -> Dict[str, Any]:
    if len(raw) != 16:
        raise ValueError(
            f"LIVE_DNA payload length unexpected: expected 16, got {len(raw)}"
        )

    word0, word1, word2, word3 = struct.unpack("<IIII", bytes(data))

    print_header("LIVE_DNA", uuid, via)
    print(f"raw_bytes: {raw}")
    print(f"word0: {word0} (0x{word0:08X})")
    print(f"word1: {word1} (0x{word1:08X})")
    print(f"word2: {word2} (0x{word2:08X})")
    print(f"word3: {word3} (0x{word3:08X})")
    sys.stdout.flush()

    return {
        "time": now_str(),
        "live_dna_raw_bytes": raw,
        "live_dna_word0": word0,
        "live_dna_word1": word1,
        "live_dna_word2": word2,
        "live_dna_word3": word3,
        "_graph_live_dna_values": [word0, word1, word2, word3],
    }


def print_battery_packet(raw: List[int], uuid: str, via: str) -> Dict[str, Any]:
    print_header("BATTERY", uuid, via)
    print(f"raw_bytes: {raw}")
    if raw:
        print(f"battery_level_percent: {raw[0]}")
    sys.stdout.flush()

    result: Dict[str, Any] = {
        "time": now_str(),
        "battery_raw_bytes": raw,
    }
    if raw:
        result["battery_level_percent"] = raw[0]
    return result


def print_bytes_packet(
    label: str, raw: List[int], uuid: str, via: str
) -> Dict[str, Any]:
    print_header(label, uuid, via)
    print(f"raw_bytes: {raw}")
    sys.stdout.flush()

    prefix = label.lower()
    return {
        "time": now_str(),
        f"{prefix}_raw_bytes": raw,
    }


def handle_payload(target: Dict[str, Any], data: bytearray, via: str) -> None:
    label = target["label"]
    uuid = target["uuid"]
    raw = bytes_to_int_list(data)

    try:
        if target["decode_mode"] == "state":
            updates = print_state_packet(raw, uuid, via)
        elif target["decode_mode"] == "live_eda":
            updates = print_live_eda_packet(raw, data, uuid, via)
        elif target["decode_mode"] == "live_dna":
            updates = print_live_dna_packet(raw, data, uuid, via)
        elif target["decode_mode"] == "battery":
            updates = print_battery_packet(raw, uuid, via)
        else:
            updates = print_bytes_packet(label, raw, uuid, via)

        if target["decode_mode"] == "live_dna":
            LIVE_DNA_LOGGER.append_row(
                packet_time=updates["time"],
                packet_via=via,
                word0=updates["live_dna_word0"],
                word1=updates["live_dna_word1"],
                word2=updates["live_dna_word2"],
                word3=updates["live_dna_word3"],
            )

        updates["last_packet_source"] = uuid
        updates["last_status"] = f"{label.lower()} {via} packet received"
        GUI.update_values(updates)

        graph_eda_value = updates.get("_graph_live_eda_ohm")
        if graph_eda_value is not None:
            GUI.push_live_eda(updates["time"], float(graph_eda_value))

        graph_dna_values = updates.get("_graph_live_dna_values")
        if graph_dna_values is not None:
            GUI.push_live_dna(updates["time"], list(graph_dna_values))

    except Exception as exc:
        print("\n" + "!" * 100)
        print(f"CHARACTERISTIC: {label} | via={via} | uuid={uuid}")
        print(f"time: {now_str()}")
        print(f"decode_error: {exc}")
        print(f"raw_bytes: {raw}")
        sys.stdout.flush()

        GUI.update_values(
            {
                "last_packet_source": uuid,
                "last_status": f"{label.lower()} {via} decode_error: {exc}",
            }
        )


def make_notify_handler(target: Dict[str, Any]) -> Callable[[Any, bytearray], None]:
    def handler(_: Any, data: bytearray) -> None:
        handle_payload(target, data, "notify")

    return handler


async def find_nuanic_device() -> Optional[Any]:
    print(f"Scanning for BLE devices for {SCAN_SECONDS} seconds...")
    GUI.update_values(
        {
            "last_status": f"scanning for {TARGET_NAME}",
            "connect_status": "SCANNING",
        }
    )

    devices = await BleakScanner.discover(timeout=SCAN_SECONDS)
    if not devices:
        GUI.update_values({"last_status": "no BLE devices found"})
        return None

    print("\nDevices found:")
    for device in devices:
        print(f"  Name: {(device.name or '(no name)'):30} Address: {device.address}")

    for device in devices:
        if (device.name or "").strip() == TARGET_NAME:
            return device

    for device in devices:
        if TARGET_NAME.lower() in (device.name or "").lower():
            return device

    return None


async def read_once(client: BleakClient, target: Dict[str, Any]) -> None:
    prefix = target_prefix(target["label"])
    try:
        data = await client.read_gatt_char(target["uuid"])
        GUI.update_values({f"{prefix}_read_status": "OK"})
        handle_payload(target, data, "read")
    except Exception as exc:
        GUI.update_values(
            {
                f"{prefix}_read_status": f"FAIL: {exc}",
                "last_status": f"{target['label'].lower()} read failed: {exc}",
            }
        )


async def poll_read_loop(
    client: BleakClient, readable_targets: List[Dict[str, Any]]
) -> None:
    while True:
        for target in readable_targets:
            await read_once(client, target)
            await asyncio.sleep(0.05)
        await asyncio.sleep(READ_POLL_SECONDS)


async def start_notify_if_supported(
    client: BleakClient, target: Dict[str, Any]
) -> bool:
    label = target["label"]
    prefix = target_prefix(label)
    info = find_characteristic_info(client, target["uuid"])

    if info is None:
        GUI.update_values(
            {
                f"{prefix}_found": "NO",
                f"{prefix}_props": "MISSING",
                f"{prefix}_notify_status": "MISSING",
                f"{prefix}_read_status": "MISSING",
            }
        )
        print(f"[MISSING] {label}: {target['uuid']}")
        return False

    props = ", ".join(info["properties"])
    GUI.update_values(
        {
            f"{prefix}_found": "YES",
            f"{prefix}_props": props,
        }
    )

    notify_capable = any(
        prop.lower() in ("notify", "indicate") for prop in info["properties"]
    )
    if not notify_capable:
        GUI.update_values({f"{prefix}_notify_status": "SKIP: not notify-capable"})
        return False

    try:
        await client.start_notify(target["uuid"], make_notify_handler(target))
        GUI.update_values({f"{prefix}_notify_status": "OK"})
        print(f"[OK] Notifications started on {label}: {target['uuid']}")
        return True
    except Exception as exc:
        GUI.update_values(
            {
                f"{prefix}_notify_status": f"FAIL: {exc}",
                "last_status": f"{label.lower()} notify failed: {exc}",
            }
        )
        print(f"[FAIL] start_notify failed for {label} {target['uuid']}: {exc}")
        return False


def get_readable_targets(
    client: BleakClient, targets: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    readable: List[Dict[str, Any]] = []

    for target in targets:
        prefix = target_prefix(target["label"])
        info = find_characteristic_info(client, target["uuid"])

        if info is None:
            GUI.update_values(
                {
                    f"{prefix}_found": "NO",
                    f"{prefix}_props": "MISSING",
                    f"{prefix}_read_status": "MISSING",
                    f"{prefix}_notify_status": "MISSING",
                }
            )
            continue

        props = ", ".join(info["properties"])
        GUI.update_values(
            {
                f"{prefix}_found": "YES",
                f"{prefix}_props": props,
            }
        )

        if any(prop.lower() == "read" for prop in info["properties"]):
            readable.append(target)
            GUI.update_values({f"{prefix}_read_status": "READY"})
        else:
            GUI.update_values({f"{prefix}_read_status": "SKIP: not readable"})

    return readable


async def run() -> None:
    device = await find_nuanic_device()
    if device is None:
        raise RuntimeError(
            f"Could not find a BLE device with name matching '{TARGET_NAME}'.\n"
            "Make sure Bluetooth is on, the ring awake, and no other app has the connection."
        )

    print(f"\nFound target device: {device.name} [{device.address}]")
    GUI.update_values(
        {
            "device_name": device.name or "(no name)",
            "device_address": device.address,
            "connect_status": "CONNECTING",
            "last_status": "device found, connecting",
        }
    )

    async with BleakClient(
        device, timeout=CONNECT_TIMEOUT, pair=PAIR_BEFORE_GATT
    ) as client:
        if not client.is_connected:
            raise RuntimeError("BLE connection failed")

        print("Connected.")
        GUI.update_values(
            {
                "connect_status": "CONNECTED",
                "last_status": "connected",
            }
        )

        await asyncio.sleep(1.0)

        service_found = any(
            normalize_uuid(service.uuid) == normalize_uuid(SERVICE_UUID)
            for service in client.services
        )
        GUI.update_values({"service_found": "YES" if service_found else "NO"})

        print("\nDiscovering services and characteristics...")
        for service in client.services:
            print(f"[Service] {service.uuid} | {service.description}")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"    [Char] {char.uuid} | {char.description} | props: {props}")

        readable_targets = get_readable_targets(client, TARGETS)

        started_notify_uuids: List[str] = []
        for target in TARGETS:
            if await start_notify_if_supported(client, target):
                started_notify_uuids.append(target["uuid"])

        for target in readable_targets:
            await read_once(client, target)

        print("\nSummary:")
        print(f"  Service found: {service_found}")
        print(f"  Target UUID count: {len(TARGETS)}")
        print(f"  Read-capable targets: {len(readable_targets)}")
        print(f"  Notify-started targets: {len(started_notify_uuids)}")

        GUI.update_values(
            {
                "last_status": (
                    f"connected, LIVE_DNA CSV logging to {LIVE_DNA_LOGGER.csv_path.name}, "
                    f"polling {len(readable_targets)} readable target(s), "
                    f"{len(started_notify_uuids)} notification subscription(s)"
                )
            }
        )

        read_task: Optional[asyncio.Task] = None
        if readable_targets:
            read_task = asyncio.create_task(poll_read_loop(client, readable_targets))

        try:
            while True:
                await asyncio.sleep(1.0)
        finally:
            if read_task is not None:
                read_task.cancel()
                try:
                    await read_task
                except asyncio.CancelledError:
                    pass

            for uuid in started_notify_uuids:
                try:
                    await client.stop_notify(uuid)
                    print(f"Stopped notify on: {uuid}")
                except Exception as exc:
                    print(f"Could not stop notify on {uuid}: {exc}")

            GUI.update_values(
                {
                    "connect_status": "DISCONNECTED",
                    "last_status": "disconnected",
                }
            )
            print("Disconnected.")


if __name__ == "__main__":
    try:
        if sys.platform.startswith("win"):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nStopped by user.")
        GUI.update_values(
            {
                "connect_status": "STOPPED",
                "last_status": "stopped by user",
            }
        )
    except Exception as exc:
        print(f"fatal_error: {exc}")
        GUI.update_values(
            {
                "connect_status": "ERROR",
                "last_status": f"fatal_error: {exc}",
            }
        )
        sys.exit(1)
