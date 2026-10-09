"""Figures and Markdown report for window-level cross-device validation.

Artifact windows are always drawn (as open markers / shading), never silently
dropped: the primary result is on all windows, the artifact-free one is a
sensitivity analysis.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .validation import agreement

REF = "#2ca02c"
TEST = "#ff7f0e"


def _bland_altman(
    ax: Any, w: pd.DataFrame, ref: str, test: str, art: str, log_ratio: bool, unit: str
) -> None:
    ok = w[[ref, test]].notna().all(axis=1)
    if log_ratio:
        ok &= (w[ref] > 0) & (w[test] > 0)
    d = w[ok]
    x, y = d[ref].to_numpy(dtype=float), d[test].to_numpy(dtype=float)
    mean = (x + y) / 2.0
    diff = y / x if log_ratio else y - x
    is_art = d[art].to_numpy(dtype=bool) if art in d else np.zeros(len(d), bool)
    ax.scatter(mean[~is_art], diff[~is_art], c=TEST, label="clean window")
    ax.scatter(
        mean[is_art],
        diff[is_art],
        facecolors="none",
        edgecolors=TEST,
        label="artifact window",
    )
    a = agreement(x, y, log_ratio=log_ratio, n_boot=200)
    if a.get("n", 0) >= 3:
        for key, style in (("bias", "-"), ("loa_lower", "--"), ("loa_upper", "--")):
            ax.axhline(a[key], color="k", linestyle=style, linewidth=1)
            if key != "bias":
                ax.axhspan(
                    a[f"{key}_ci_low"], a[f"{key}_ci_high"], color="grey", alpha=0.15
                )
    if log_ratio:
        ax.set_xscale("log")
        ax.set_yscale("log")
    ax.set_xlabel(f"Mean of methods ({unit})")
    ax.set_ylabel(
        "Ratio test / reference" if log_ratio else f"Test - reference ({unit})"
    )
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, linestyle="--", alpha=0.4)


def generate_validation_plots(windows: pd.DataFrame, output_dir: Path) -> list[Path]:
    """Bland-Altman (HR, RMSSD) and time-series figures; returns the saved paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    if windows.empty or "ref_hr" not in windows:
        return paths
    w = windows[windows["ref_ok"]] if "ref_ok" in windows else windows

    for ref, test, art, log_ratio, unit, name, title in (
        ("ref_hr", "ppg_hr", "artifact", False, "BPM", "bland_altman_hr.png", "HR"),
        (
            "ref_rmssd",
            "ppg_rmssd",
            "artifact",
            True,
            "ms",
            "bland_altman_rmssd.png",
            "RMSSD",
        ),
    ):
        if test not in w or w[test].notna().sum() < 3:
            continue
        fig, ax = plt.subplots(figsize=(7, 5))
        _bland_altman(ax, w, ref, test, art, log_ratio, unit)
        ax.set_title(f"Bland-Altman: PPG {title} vs H10 RR (bands: 95 % CI of LoA)")
        fig.tight_layout()
        fig.savefig(output_dir / name, dpi=150)
        plt.close(fig)
        paths.append(output_dir / name)

    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    for ax, ref, test, unit in (
        (axes[0], "ref_hr", "ppg_hr", "HR (BPM)"),
        (axes[1], "ref_rmssd", "ppg_rmssd", "RMSSD (ms)"),
    ):
        ax.plot(w["start"], w[ref], "o-", color=REF, label="H10 RR (reference)")
        if test in w:
            ax.plot(w["start"], w[test], "s--", color=TEST, label="Verity Sense PPG")
        if "artifact" in w:
            for start in w.loc[w["artifact"].astype(bool), "start"]:
                ax.axvspan(
                    start, start + (w["start"].diff().median()), color="red", alpha=0.1
                )
        ax.set_ylabel(unit)
        ax.grid(True, linestyle="--", alpha=0.4)
    axes[0].legend(loc="best", fontsize=8)
    axes[0].set_title("Per-window agreement (red = Sense artifact window)")
    fig.tight_layout()
    fig.savefig(output_dir / "time_series.png", dpi=150)
    plt.close(fig)
    paths.append(output_dir / "time_series.png")
    return paths


def _fmt(v: Any, spec: str = ".2f") -> str:
    return "-" if v is None or not np.isfinite(v) else format(v, spec)


def _result_rows(label: str, res: dict[str, Any]) -> list[str]:
    ratio = res.get("log_ratio")
    unit = "×" if ratio else ""
    if res.get("n", 0) < 3:
        return [f"| {label} | {res.get('n', 0)} | - | - | - | - | - | - | - |"]
    loa = (
        f"{_fmt(res['loa_lower'])}{unit} [{_fmt(res['loa_lower_ci_low'])}, "
        f"{_fmt(res['loa_lower_ci_high'])}] to {_fmt(res['loa_upper'])}{unit} "
        f"[{_fmt(res['loa_upper_ci_low'])}, {_fmt(res['loa_upper_ci_high'])}]"
    )
    bias = f"{_fmt(res['bias'])}{unit} [{_fmt(res['bias_ci_low'])}, {_fmt(res['bias_ci_high'])}]"
    grades = res.get("grades", {})
    return [
        f"| {label} | {res['n']} | {bias} | {loa} "
        f"| {_fmt(res['prop_bias_slope'], '.3f')} (p={_fmt(res['prop_bias_p'], '.3f')}) "
        f"| {_fmt(res['mae'])} [{_fmt(res['mae_ci_low'])}, {_fmt(res['mae_ci_high'])}] "
        f"| {_fmt(res['mape'])} % {('(' + grades['mape'] + ')') if grades else ''} "
        f"| {_fmt(res['lins_ccc'], '.3f')} {('(' + grades['lins_ccc'] + ')') if grades else ''} "
        f"| {_fmt(res['icc_2_1'], '.3f')} {('(' + grades['icc_2_1'] + ')') if grades else ''} |"
    ]


def generate_markdown_report(
    results: list[dict[str, Any]],
    session_id: str,
    windows: pd.DataFrame,
    window_s: int,
    pooled: list[dict[str, Any]] | None = None,
) -> str:
    """Markdown report: methods, per-comparison agreement (all / clean), windows."""
    n_art = int(windows["artifact"].sum()) if "artifact" in windows else 0
    lines = [
        "# Polar Verity Sense vs H10: Agreement Report",
        "",
        f"**Session**: `{session_id}`  ",
        f"**Windows**: {len(windows)} × {window_s} s, non-overlapping, host clock  ",
        "**Reference**: H10 RR intervals (ECG-derived on device, 1/1024 s), cleaned "
        "(300-2000 ms, ±20 % of local median; invalid beats excluded, successive "
        "differences only between adjacent valid intervals)  ",
        "**Test**: Verity Sense raw PPG beats (band-pass 0.5-4 Hz, interpolated peaks, "
        "best channel per window by spectral SQI) and, if recorded, the Sense PPI stream  ",
        f"**Artifact windows**: {n_art} (Sense accelerometer motion, PPG SQI, coverage, "
        "skin contact; never the reference)",
        "",
        "Bias and limits of agreement (LoA) are shown with 95 % CIs; RMSSD uses "
        "log-transformed limits reported as ratios (test/reference). MAE CIs come from "
        "a moving-block bootstrap over windows. Proportional bias = slope of the "
        "difference on the mean. Grades only where a published standard exists "
        "(MAPE: ANSI/CTA-2065; CCC: McBride 2005; ICC: Koo & Li 2016).",
        "",
    ]
    header = [
        "| Comparison | n | Bias [95 % CI] | LoA [95 % CI] | Prop. bias | MAE [95 % CI] | MAPE | CCC | ICC(2,1) |",
        "| :--- | ---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for key, title in (
        ("all", "## Primary: all windows with a valid reference"),
        ("clean", "## Sensitivity: artifact windows excluded"),
    ):
        lines += [title, "", *header]
        for res in results:
            if key in res:
                lines += _result_rows(res["label"], res[key])
        lines.append("")

    if pooled:
        lines += [
            "## Pooled over participants (Bland & Altman 2007, cluster bootstrap)",
            "",
            "| Comparison | Participants | Windows | Bias [95 % CI] | LoA [95 % CI] |",
            "| :--- | ---: | ---: | :--- | :--- |",
        ]
        for p in pooled:
            if "bias" not in p:
                continue
            u = "×" if p["log_ratio"] else ""
            lines.append(
                f"| {p['label']} | {p['n_subjects']} | {p['n_windows']} "
                f"| {_fmt(p['bias'])}{u} [{_fmt(p['bias_ci_low'])}, {_fmt(p['bias_ci_high'])}] "
                f"| {_fmt(p['loa_lower'])}{u} [{_fmt(p['loa_lower_ci_low'])}, {_fmt(p['loa_lower_ci_high'])}]"
                f" to {_fmt(p['loa_upper'])}{u} [{_fmt(p['loa_upper_ci_low'])}, {_fmt(p['loa_upper_ci_high'])}] |"
            )
        lines.append("")

    cols = [
        c
        for c in (
            "start",
            "ref_hr",
            "ppg_hr",
            "ref_rmssd",
            "ppg_rmssd",
            "ppg_sqi",
            "motion_frac",
            "artifact_reason",
            "markers",
        )
        if c in windows
    ]
    lines += [
        "## Windows",
        "",
        "| " + " | ".join(cols) + " |",
        "|" + " --- |" * len(cols),
    ]
    for _, row in windows[cols].iterrows():
        cells = [
            row[c].strftime("%H:%M:%S")
            if c == "start"
            else _fmt(row[c])
            if isinstance(row[c], float)
            else str(row[c])
            for c in cols
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


# --- Feature extraction (research.features) ------------------------------------

PPI = "#1f77b4"
SOURCES = (
    ("rr", "H10 RR", REF),
    ("ppi", "Sense PPI", PPI),
    ("ppgbeat", "Sense PPG", TEST),
)
# (column, label, unit); ECG rows are summarised over windows without ecg_artifact
FEATURE_SUMMARY = (
    ("rr_hr", "H10 HR", "BPM"),
    ("rr_sdnn", "H10 SDNN", "ms"),
    ("rr_rmssd", "H10 RMSSD", "ms"),
    ("rr_pnn50", "H10 pNN50", "%"),
    ("rr_sd1", "H10 SD1", "ms"),
    ("rr_sd2", "H10 SD2", "ms"),
    ("rr_vlf_5m", "H10 VLF power (5 min)", "ms²"),
    ("rr_lf_5m", "H10 LF power (5 min)", "ms²"),
    ("rr_hf_5m", "H10 HF power (5 min)", "ms²"),
    ("rr_lf_hf_5m", "H10 LF/HF (5 min)", ""),
    ("rr_sampen_5m", "H10 sample entropy (5 min)", ""),
    ("rr_dfa_a1_5m", "H10 DFA α1 (5 min)", ""),
    ("ppi_rmssd", "Sense PPI RMSSD", "ms"),
    ("ppi_lf_hf_5m", "Sense PPI LF/HF (5 min)", ""),
    ("ppgbeat_rmssd", "Sense PPG RMSSD", "ms"),
    ("ppgbeat_lf_hf_5m", "Sense PPG LF/HF (5 min)", ""),
    ("ecg_good_beats", "ECG fully delineated beats", "fraction"),
    ("ecg_quality", "ECG quality (NeuroKit2)", "0-1"),
    ("ecg_r_amp", "R amplitude", "µV"),
    ("ecg_q_depth", "Q depth", "µV"),
    ("ecg_s_depth", "S depth", "µV"),
    ("ecg_p_amp", "P amplitude", "µV"),
    ("ecg_p_dur", "P duration", "ms"),
    ("ecg_qrs_dur", "QRS duration", "ms"),
    ("ecg_t_amp", "T amplitude", "µV"),
    ("ecg_t_dur", "T duration", "ms"),
    ("ecg_pr", "PR interval", "ms"),
    ("ecg_qt", "QT interval", "ms"),
    ("ecg_qtc_bazett", "QTc (Bazett)", "ms"),
    ("ecg_qtc_fridericia", "QTc (Fridericia)", "ms"),
    ("ecg_st_level", "ST level, J+60 ms (not diagnostic)", "µV"),
)


def generate_feature_summary(features: pd.DataFrame) -> str:
    """Markdown section: per-feature median and IQR over windows."""
    lines = [
        "## Feature summary",
        "",
        f"{len(features)} windows. `(5 min)` features use a 300 s window centred on "
        "each row, so neighbouring rows share data. ECG rows exclude windows flagged "
        "`ecg_artifact` (under half the beats fully delineated, NeuroKit2 quality "
        "< 0.5, or H10 motion). Single chest lead at 130 Hz: intervals are quantised "
        "to 7.7 ms and the ST level is not diagnostic.",
        "",
        "| Feature | Unit | Windows | Median | IQR |",
        "| :--- | :--- | ---: | ---: | :--- |",
    ]
    clean = (
        features[~features["ecg_artifact"].astype(bool)]
        if "ecg_artifact" in features
        else features
    )
    for col, label, unit in FEATURE_SUMMARY:
        rows = clean if col.startswith("ecg_") else features
        if col not in rows:
            continue
        v = pd.to_numeric(rows[col], errors="coerce").dropna()
        if v.empty:
            continue
        q1, med, q3 = v.quantile([0.25, 0.5, 0.75])
        lines.append(
            f"| {label} | {unit} | {len(v)} | {_fmt(med)} | {_fmt(q1)} to {_fmt(q3)} |"
        )
    return "\n".join(lines) + "\n"


def _shade_artifacts(ax: Any, features: pd.DataFrame) -> None:
    if "ecg_artifact" not in features:
        return
    step = features["start"].diff().median()
    for start in features.loc[features["ecg_artifact"].astype(bool), "start"]:
        ax.axvspan(start, start + step, color="grey", alpha=0.2)


def _valid_beats(d: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Beat times (s), intervals (ms) and validity of one interval source."""
    from polar_ble_sdk.metrics.hrv import rr_valid_mask

    ms = d["ms"].to_numpy(dtype=float)
    ok = np.array(rr_valid_mask([None if np.isnan(v) else v for v in ms]), bool)
    t = (d["t"] - d["t"].iloc[0]).dt.total_seconds().to_numpy()
    return t, ms, ok


def generate_feature_plots(
    features: pd.DataFrame, signals: Any, output_dir: Path
) -> list[Path]:
    """Feature timeline, average ECG beat, HRV spectra and Poincaré plots.

    ``signals`` is the :class:`~polar_ble_sdk.research.features.SessionSignals`
    the features were extracted from.
    """
    from .features import ECG_QUALITY_MIN, HF, LF, TEMPLATE_S, lomb_psd

    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    def save(fig: Any, name: str) -> None:
        fig.tight_layout()
        fig.savefig(output_dir / name, dpi=150)
        plt.close(fig)
        paths.append(output_dir / name)

    if not features.empty:
        fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
        for ax, suffix, unit in (
            (axes[0], "hr", "HR (BPM)"),
            (axes[1], "lf_hf_5m", "LF/HF (5 min)"),
        ):
            for src, label, color in SOURCES:
                if f"{src}_{suffix}" in features:
                    ax.plot(
                        features["start"],
                        features[f"{src}_{suffix}"],
                        "o-",
                        color=color,
                        label=label,
                    )
            ax.set_ylabel(unit)
        for col, style, label in (
            ("ecg_qtc_bazett", "o-", "Bazett"),
            ("ecg_qtc_fridericia", "s--", "Fridericia"),
        ):
            if col in features:
                axes[2].plot(
                    features["start"], features[col], style, color="k", label=label
                )
        axes[2].set_ylabel("QTc (ms)")
        for ax in axes:
            _shade_artifacts(ax, features)
            ax.grid(True, linestyle="--", alpha=0.4)
            if ax.get_legend_handles_labels()[0]:
                ax.legend(loc="best", fontsize=8)
        axes[0].set_title("Features per window (grey = ECG artifact window)")
        save(fig, "feature_timeline.png")

    beats, tpl = signals.ecg_beats, signals.ecg_templates
    if len(tpl):
        keep = (
            beats["complete"].to_numpy(dtype=bool)
            & (beats["quality"].to_numpy() >= ECG_QUALITY_MIN)
            & ~np.isnan(tpl).any(axis=1)
        )
        good = tpl[keep]
        if len(good):
            t_ms = np.linspace(-TEMPLATE_S[0], TEMPLATE_S[1], tpl.shape[1]) * 1000
            fig, ax = plt.subplots(figsize=(8, 5))
            for row in good[:: max(1, len(good) // 200)]:
                ax.plot(t_ms, row, color="grey", alpha=0.1, linewidth=0.5)
            ax.plot(
                t_ms,
                np.median(good, axis=0),
                color="k",
                linewidth=2,
                label="median beat",
            )
            lo, hi = np.percentile(good, [2, 98])
            ax.set_ylim(lo - 0.1 * (hi - lo), hi + 0.1 * (hi - lo))
            marks = [("R", 0.0)] + [
                (n[0], beats.loc[keep, f"{n}_ms"].median())
                for n in ("P_Peaks", "Q_Peaks", "S_Peaks", "T_Peaks")
            ]
            for name, pos in marks:
                if np.isfinite(pos):
                    ax.axvline(pos, color=TEST, linestyle="--", linewidth=1)
                    ax.text(
                        pos,
                        1.0,
                        name,
                        transform=ax.get_xaxis_transform(),
                        ha="center",
                        va="bottom",
                    )
            ax.set_xlabel("Time from R peak (ms)")
            ax.set_ylabel("ECG (µV, cleaned)")
            ax.set_title(
                f"Average beat: {len(good)} fully delineated H10 beats "
                f"(quality >= {ECG_QUALITY_MIN})",
                pad=16,
            )
            ax.legend(loc="lower right", fontsize=8)
            ax.grid(True, linestyle="--", alpha=0.4)
            save(fig, "average_beat.png")

    sources = [s for s in SOURCES if s[0] in signals.intervals]
    if sources:
        fig, ax = plt.subplots(figsize=(8, 5))
        for src, label, color in sources:
            t, ms, ok = _valid_beats(signals.intervals[src])
            if ok.sum() >= 50:
                f, p = lomb_psd(t[ok], ms[ok])
                ax.plot(f, p, color=color, label=label)
        for (lo, hi), name in ((LF, "LF"), (HF, "HF")):
            ax.axvspan(lo, hi, color="grey", alpha=0.1 if name == "LF" else 0.2)
            ax.text(
                (lo + hi) / 2,
                1.0,
                name,
                transform=ax.get_xaxis_transform(),
                ha="center",
                va="bottom",
            )
        ax.set_xlim(0, 0.5)
        ax.set_yscale("log")
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel("PSD (ms²/Hz)")
        ax.set_title("HRV spectrum, whole recording (Lomb-Scargle)", pad=16)
        ax.legend(loc="best", fontsize=8)
        ax.grid(True, linestyle="--", alpha=0.4)
        save(fig, "hrv_psd.png")

        fig, axes = plt.subplots(
            1, len(sources), figsize=(5 * len(sources), 5), squeeze=False
        )
        for ax, (src, label, color) in zip(axes[0], sources, strict=True):
            _, ms, ok = _valid_beats(signals.intervals[src])
            pair = ok[:-1] & ok[1:]
            ax.scatter(ms[:-1][pair], ms[1:][pair], s=6, color=color, alpha=0.6)
            if ok.any():
                lim = [float(np.min(ms[ok])), float(np.max(ms[ok]))]
                ax.plot(lim, lim, color="k", linewidth=0.8)
            ax.set_xlabel("RR$_n$ (ms)")
            ax.set_ylabel("RR$_{n+1}$ (ms)")
            ax.set_title(f"Poincaré: {label}")
            ax.set_aspect("equal", adjustable="datalim")
            ax.grid(True, linestyle="--", alpha=0.4)
        save(fig, "poincare.png")
    return paths
