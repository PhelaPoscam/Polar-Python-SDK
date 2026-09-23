"""Dual-Device cross-validation analysis CLI (Polar H10 vs Polar Verity Sense).

Usage:
    python scripts/run_analysis.py [session_dir] [--window 60]
    python scripts/run_analysis.py --pool SESSION_DIR [SESSION_DIR ...]

Per session: fixed windows on the host clock, Verity Sense PPG/PPI against the
H10 RR reference, metrics on all windows (primary) and artifact-free windows
(sensitivity). ``--pool`` adds Bland-Altman (2007) repeated-measures limits
across participants (``participant_id`` in session_meta.json, else session id).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

from polar_ble_sdk.research import (  # noqa: E402
    build_windows,
    generate_markdown_report,
    generate_validation_plots,
    load_session,
    repeated_measures_agreement,
    validate_windows,
    verify_session_integrity,
)
from polar_ble_sdk.research.validation import COMPARISONS  # noqa: E402
from polar_ble_sdk.research.windows import WINDOW_S  # noqa: E402


def find_latest_session_dir() -> Path | None:
    """Find the most recent session directory in data/dual/ or data/."""
    dual_dir = PROJECT_ROOT / "data" / "dual"
    if dual_dir.exists():
        subdirs = [p for p in dual_dir.iterdir() if p.is_dir()]
        if subdirs:
            subdirs.sort(key=lambda p: p.name, reverse=True)
            return subdirs[0]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Polar Dual-Device Cross-Validation Analysis"
    )
    parser.add_argument(
        "session_dir",
        nargs="?",
        type=str,
        default=None,
        help="Path to session directory",
    )
    parser.add_argument(
        "--window", type=int, default=WINDOW_S, help="Window length in seconds."
    )
    parser.add_argument(
        "--pool",
        nargs="+",
        default=None,
        metavar="SESSION_DIR",
        help="Pool several sessions (repeated-measures limits of agreement).",
    )
    args = parser.parse_args()

    console = Console()
    if args.pool:
        _pooled_analysis([Path(p).resolve() for p in args.pool], args.window, console)
        return

    if args.session_dir:
        session_path = Path(args.session_dir).resolve()
    else:
        latest = find_latest_session_dir()
        if not latest:
            console.print(
                "[bold red]No session directory specified and no recorded sessions found in data/dual/.[/bold red]"
            )
            sys.exit(1)
        session_path = latest

    if not session_path.exists():
        console.print(
            f"[bold red]Session directory does not exist: {session_path}[/bold red]"
        )
        sys.exit(1)

    console.print(f"\n[bold cyan]Analyzing Session:[/bold cyan] {session_path.name}")
    console.print(f"[dim]Directory: {session_path}[/dim]\n")

    # 1. Load Session Data
    session = load_session(session_path)
    if not session:
        console.print("[bold red]Failed to load session data.[/bold red]")
        sys.exit(1)

    # 2. Signal Integrity Audit
    audit_data = verify_session_integrity(session_path)
    if audit_data:
        audit_table = Table(
            title="Signal Integrity & Sampling Rate Audit", title_style="bold cyan"
        )
        audit_table.add_column("Device / Stream", style="bold")
        audit_table.add_column("Actual (Hz)", justify="right")
        audit_table.add_column("Std Dev (Hz)", justify="right")
        audit_table.add_column("Samples", justify="right")
        audit_table.add_column("Duration (s)", justify="right")
        audit_table.add_column("Gaps (>2x)", justify="right")
        audit_table.add_column("Max Gap (s)", justify="right")

        for dev_key in ("h10", "sense", "streams"):
            if dev_key in audit_data and isinstance(audit_data[dev_key], dict):
                for s_name, a in audit_data[dev_key].items():
                    audit_table.add_row(
                        f"{dev_key.upper()} - {s_name}",
                        f"{a['average_hz']:.2f}",
                        f"{a['std_dev_hz']:.2f}",
                        str(a["sample_count"]),
                        f"{a['duration_s']:.1f}",
                        str(a["gap_count"]),
                        f"{a['max_gap_s']:.3f}",
                    )
        console.print(audit_table)
        console.print()

    # 3. Window-level validation against the H10 RR reference
    windows = build_windows(session_path, window_s=args.window)
    if windows.empty:
        console.print(
            "[bold red]No overlapping H10 RR and Sense data (needs raw hr.csv and "
            "ppg.csv or ppi.csv, plus host zero points from a v1.1+ recording).[/bold red]"
        )
        sys.exit(1)
    results = validate_windows(windows)
    _print_results(console, results, windows, args.window)

    # 4. Reports & plots
    reports_dir = session_path / "reports"
    plots = generate_validation_plots(windows, reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "validation_report.md").write_text(
        generate_markdown_report(results, session_path.name, windows, args.window),
        encoding="utf-8",
    )
    windows.to_csv(reports_dir / "windows.csv", index=False)

    plot_info = f"\nPlots Generated: [cyan]{len(plots)} figures[/cyan]" if plots else ""
    console.print(
        Panel(
            f"[bold green]Analysis complete![/bold green]\n"
            f"Session: [cyan]{session_path.name}[/cyan]\n"
            f"Reports: [cyan]{reports_dir}[/cyan]{plot_info}",
            title="Analysis Status",
            border_style="green",
        )
    )


def _fmt(v: float, spec: str = ".2f") -> str:
    return format(v, spec) if v is not None and np.isfinite(v) else "-"


def _print_results(
    console: Console, results: list[dict], windows: pd.DataFrame, window_s: int
) -> None:
    n_art = int(windows["artifact"].sum()) if "artifact" in windows else 0
    console.print(
        f"[bold]{len(windows)} windows x {window_s} s[/bold], "
        f"{int(windows['ref_ok'].sum())} with a complete reference, "
        f"{n_art} Sense artifact windows\n"
    )
    for key, title in (
        ("all", "Primary: all windows"),
        ("clean", "Sensitivity: artifact-free"),
    ):
        table = Table(title=f"{title} (vs H10 RR)", title_style="bold cyan")
        for col in (
            "Comparison",
            "n",
            "Bias [95% CI]",
            "LoA",
            "MAE",
            "MAPE",
            "CCC",
            "ICC",
        ):
            table.add_column(col, justify="left" if col == "Comparison" else "right")
        for res in results:
            r = res.get(key)
            if not r or r.get("n", 0) < 3:
                continue
            u = "x" if r["log_ratio"] else ""
            table.add_row(
                res["label"],
                str(r["n"]),
                f"{_fmt(r['bias'])}{u} [{_fmt(r['bias_ci_low'])}, {_fmt(r['bias_ci_high'])}]",
                f"{_fmt(r['loa_lower'])}{u} to {_fmt(r['loa_upper'])}{u}",
                _fmt(r["mae"]),
                f"{_fmt(r['mape'])} %",
                _fmt(r["lins_ccc"], ".3f"),
                _fmt(r["icc_2_1"], ".3f"),
            )
        console.print(table)
        console.print()


def _pooled_analysis(sessions: list[Path], window_s: int, console: Console) -> None:
    frames = []
    for path in sessions:
        w = build_windows(path, window_s=window_s)
        if w.empty:
            console.print(f"[yellow]Skipping {path.name}: no usable windows[/yellow]")
            continue
        meta = load_session(path).metadata
        w["participant"] = meta.get("participant_id") or path.name
        frames.append(w)
    if not frames:
        console.print("[bold red]No usable sessions.[/bold red]")
        sys.exit(1)
    all_w = pd.concat(frames, ignore_index=True)
    all_w = all_w[all_w["ref_ok"]]
    pooled = []
    for label, ref_col, test_col, art_col, log_ratio in COMPARISONS:
        if test_col not in all_w:
            continue
        subsets = [("all", all_w)]
        if art_col and art_col in all_w:
            subsets.append(("clean", all_w[~all_w[art_col].astype(bool)]))
        for subset, rows in subsets:
            res = repeated_measures_agreement(
                rows, "participant", ref_col, test_col, log_ratio=log_ratio
            )
            res["label"] = f"{label} ({subset})"
            pooled.append(res)

    table = Table(title="Pooled over participants (Bland & Altman 2007)")
    for col in (
        "Comparison",
        "Participants",
        "Windows",
        "Bias [95% CI]",
        "LoA [95% CI]",
    ):
        table.add_column(col)
    for p in pooled:
        if "bias" not in p:
            continue
        u = "x" if p["log_ratio"] else ""
        table.add_row(
            p["label"],
            str(p["n_subjects"]),
            str(p["n_windows"]),
            f"{_fmt(p['bias'])}{u} [{_fmt(p['bias_ci_low'])}, {_fmt(p['bias_ci_high'])}]",
            f"{_fmt(p['loa_lower'])}{u} [{_fmt(p['loa_lower_ci_low'])}, "
            f"{_fmt(p['loa_lower_ci_high'])}] to {_fmt(p['loa_upper'])}{u} "
            f"[{_fmt(p['loa_upper_ci_low'])}, {_fmt(p['loa_upper_ci_high'])}]",
        )
    console.print(table)


if __name__ == "__main__":
    main()
