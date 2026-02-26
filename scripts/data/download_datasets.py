"""
Dataset setup helper for WESAD, SWELL, and UBFC-Phys.

This script does not download data automatically because these datasets
have different access rules and licensing requirements. Instead, it:
- validates the expected folder layout
- optionally extracts ZIP archives into the proper dataset folders
"""

from __future__ import annotations

import argparse
import os
import sys
import zipfile


DATASET_LAYOUT = {
    "WESAD": "WESAD",
    "SWELL": "SWELL",
    "UBFC-Phys": "UBFC-Phys",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify local dataset layout and extract archives.")
    parser.add_argument(
        "--data-dir",
        default="datasets",
        help="Base directory for datasets (default: datasets).",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify dataset presence and exit.",
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="Extract ZIP files from datasets/archives into dataset folders.",
    )
    return parser.parse_args()


def ensure_dir(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def is_non_empty_dir(path: str) -> bool:
    return os.path.isdir(path) and any(os.scandir(path))


def verify_layout(base_dir: str) -> dict[str, bool]:
    status = {}
    for name, subdir in DATASET_LAYOUT.items():
        dataset_dir = os.path.join(base_dir, subdir)
        status[name] = is_non_empty_dir(dataset_dir)
    return status


def extract_archives(base_dir: str) -> None:
    archive_dirs = [base_dir, os.path.join(base_dir, "archives")]
    extracted = False

    for archive_dir in archive_dirs:
        if not os.path.isdir(archive_dir):
            continue
        for entry in os.listdir(archive_dir):
            if not entry.lower().endswith(".zip"):
                continue
            zip_path = os.path.join(archive_dir, entry)
            print(f"Extracting {zip_path}...")
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(base_dir)
            extracted = True

    if not extracted:
        print(f"No ZIP archives found under: {base_dir} or {os.path.join(base_dir, 'archives')}")


def print_instructions(base_dir: str, status: dict[str, bool]) -> None:
    print("\nDataset setup status:")
    for name, present in status.items():
        subdir = DATASET_LAYOUT[name]
        dataset_dir = os.path.join(base_dir, subdir)
        flag = "OK" if present else "MISSING"
        print(f"- {name}: {flag} -> {dataset_dir}")

    missing = [name for name, present in status.items() if not present]
    if missing:
        print("\nMissing datasets detected.")
        print("Download each dataset from its official source and place the raw files under:")
        for name in missing:
            print(f"- {os.path.join(base_dir, DATASET_LAYOUT[name])}")
        print("\nIf you have ZIP archives, place them under either:")
        print(f"- {base_dir}")
        print(f"- {os.path.join(base_dir, 'archives')}")
        print("Then run with --extract to unpack them.")


def main() -> int:
    args = parse_args()
    ensure_dir(args.data_dir)

    if args.extract:
        extract_archives(args.data_dir)

    status = verify_layout(args.data_dir)
    print_instructions(args.data_dir, status)

    if args.verify_only:
        return 0

    if not all(status.values()):
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
