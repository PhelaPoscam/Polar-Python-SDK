"""Agreement statistics for method comparison (Verity Sense vs H10 RR reference).

Inputs are paired values per analysis window (see :mod:`.windows`), never 1 Hz
rows: consecutive seconds of heart rate are strongly autocorrelated and would
inflate the effective sample size. Windows are still serially correlated, so
bootstrap intervals resample contiguous blocks, and pooled multi-participant
analyses resample participants.

References:
    - Bland & Altman (1999). Measuring agreement in method comparison studies.
      Stat Methods Med Res 8:135-160 (limits of agreement, their CIs, log/ratio
      limits for skewed measures such as RMSSD).
    - Bland & Altman (2007). Agreement between methods of measurement with
      multiple observations per individual. J Biopharm Stat 17:571-582.
    - Lin (1989), McBride (2005): concordance correlation and its strength bands.
    - Shrout & Fleiss (1979), Koo & Li (2016): ICC(2,1) and its interpretation.
    - ANSI/CTA-2065 (2018): heart-rate monitor accuracy, MAPE <= 10 %.
    - Hyslop & White (2009): root-mean-square within-subject CV.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

N_BOOT = 2000


def calculate_lins_ccc(x: Any, y: Any) -> float:
    """Calculate Lin's Concordance Correlation Coefficient (CCC)."""
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    valid = (~np.isnan(x_arr)) & (~np.isnan(y_arr))
    x_arr, y_arr = x_arr[valid], y_arr[valid]

    if len(x_arr) < 2:
        return float("nan")

    mean_x = float(np.mean(x_arr))
    mean_y = float(np.mean(y_arr))
    var_x = float(np.var(x_arr, ddof=0))
    var_y = float(np.var(y_arr, ddof=0))

    if var_x == 0 and var_y == 0:
        return 1.0 if mean_x == mean_y else 0.0

    cov_xy = float(np.mean((x_arr - mean_x) * (y_arr - mean_y)))
    denom = var_x + var_y + (mean_x - mean_y) ** 2
    if denom == 0:
        return float("nan")
    return (2.0 * cov_xy) / denom


def calculate_icc_2_1(x: Any, y: Any) -> float:
    """Calculate Two-way random/mixed, single-measurement absolute agreement ICC(2,1)."""
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    valid = (~np.isnan(x_arr)) & (~np.isnan(y_arr))
    x_arr, y_arr = x_arr[valid], y_arr[valid]

    n = len(x_arr)
    if n < 3:
        return float("nan")

    data = np.column_stack((x_arr, y_arr))
    grand_mean = float(np.mean(data))

    ss_total = float(np.sum((data - grand_mean) ** 2))
    row_means = np.mean(data, axis=1)
    ss_rows = 2.0 * float(np.sum((row_means - grand_mean) ** 2))
    col_means = np.mean(data, axis=0)
    ss_cols = n * float(np.sum((col_means - grand_mean) ** 2))
    ss_error = ss_total - ss_rows - ss_cols

    ms_rows = ss_rows / (n - 1)
    ms_cols = ss_cols / (2 - 1)
    ms_error = max(0.0, ss_error / ((n - 1) * (2 - 1)))

    denom = ms_rows + ms_error + (2.0 / n) * (ms_cols - ms_error)
    if denom == 0:
        return float("nan")
    return float((ms_rows - ms_error) / denom)


def calculate_wscv(x: Any, y: Any) -> float:
    """Root-mean-square coefficient of variation between the two methods (%)."""
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    pair_sd = np.abs(x_arr - y_arr) / np.sqrt(2.0)
    cv = pair_sd / ((x_arr + y_arr) / 2.0)
    return float(np.sqrt(np.nanmean(cv**2)) * 100.0)


def block_bootstrap_ci(
    x: np.ndarray,
    y: np.ndarray,
    stat_fn: Callable[[np.ndarray, np.ndarray], float],
    block_len: int | None = None,
    n_boot: int = N_BOOT,
    ci: float = 95.0,
    seed: int = 42,
) -> tuple[float, float]:
    """Percentile CI from a moving-block bootstrap over time-ordered pairs.

    Blocks of ``block_len`` (default ``n ** (1/3)``) consecutive windows keep
    their serial correlation, which an i.i.d. bootstrap would destroy.
    """
    n = len(x)
    if n < 3:
        return float("nan"), float("nan")
    block_len = block_len or max(1, round(n ** (1 / 3)))
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block_len))
    starts = rng.integers(0, n - block_len + 1, size=(n_boot, n_blocks))
    idx = (starts[:, :, None] + np.arange(block_len)).reshape(n_boot, -1)[:, :n]
    boot = np.array([stat_fn(x[i], y[i]) for i in idx])
    lo, hi = np.nanpercentile(boot, [(100 - ci) / 2, 100 - (100 - ci) / 2])
    return float(lo), float(hi)


def _loa(diff: np.ndarray) -> dict[str, float]:
    """Bias and 95 % limits of agreement with their exact-ish 95 % CIs."""
    n = len(diff)
    bias = float(np.mean(diff))
    sd = float(np.std(diff, ddof=1))
    t = float(stats.t.ppf(0.975, n - 1))
    se_bias = sd / np.sqrt(n)
    se_loa = sd * np.sqrt(3.0 / n)  # Bland & Altman (1999), eq. for LoA SE
    lower, upper = bias - 1.96 * sd, bias + 1.96 * sd
    return {
        "bias": bias,
        "bias_ci_low": bias - t * se_bias,
        "bias_ci_high": bias + t * se_bias,
        "sd_diff": sd,
        "loa_lower": lower,
        "loa_lower_ci_low": lower - t * se_loa,
        "loa_lower_ci_high": lower + t * se_loa,
        "loa_upper": upper,
        "loa_upper_ci_low": upper - t * se_loa,
        "loa_upper_ci_high": upper + t * se_loa,
    }


def agreement(
    ref: Any,
    test: Any,
    *,
    log_ratio: bool = False,
    n_boot: int = N_BOOT,
    seed: int = 42,
) -> dict[str, Any]:
    """Agreement of ``test`` against ``ref`` over time-ordered paired windows.

    ``log_ratio=True`` computes the limits on ln values and reports them as
    ratios test/ref (Bland & Altman 1999), for skewed, positive measures whose
    error grows with magnitude, such as RMSSD.
    """
    x = np.asarray(ref, dtype=float)
    y = np.asarray(test, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    if log_ratio:
        ok &= (x > 0) & (y > 0)
    x, y = x[ok], y[ok]
    n = len(x)
    out: dict[str, Any] = {"n": n, "log_ratio": log_ratio}
    if n < 3:
        return out

    diff = np.log(y) - np.log(x) if log_ratio else y - x
    loa = _loa(diff)
    if log_ratio:
        loa = {k: (float(np.exp(v)) if k != "sd_diff" else v) for k, v in loa.items()}
    out.update(loa)

    mean = (x + y) / 2.0
    fit = stats.linregress(np.log(mean) if log_ratio else mean, diff)
    out["prop_bias_slope"] = float(fit.slope)
    out["prop_bias_p"] = float(fit.pvalue)

    err = y - x
    out["mae"] = float(np.mean(np.abs(err)))
    out["mape"] = float(np.mean(np.abs(err) / x) * 100.0)
    out["rmse"] = float(np.sqrt(np.mean(err**2)))
    out["mae_ci_low"], out["mae_ci_high"] = block_bootstrap_ci(
        x, y, lambda a, b: float(np.mean(np.abs(b - a))), n_boot=n_boot, seed=seed
    )
    out["pearson_r"] = (
        float(stats.pearsonr(x, y)[0]) if np.std(x) and np.std(y) else float("nan")
    )
    out["lins_ccc"] = calculate_lins_ccc(x, y)
    out["icc_2_1"] = calculate_icc_2_1(x, y)
    out["wscv"] = calculate_wscv(x, y)
    out["x_mean"], out["y_mean"] = float(np.mean(x)), float(np.mean(y))
    return out


def repeated_measures_agreement(
    df: pd.DataFrame,
    subject_col: str,
    ref_col: str,
    test_col: str,
    *,
    log_ratio: bool = False,
    n_boot: int = N_BOOT,
    seed: int = 42,
) -> dict[str, Any]:
    """Limits of agreement pooled over participants with several windows each.

    Bland & Altman (2007), true value varying within subject: the variance of
    the differences is the between-subject component ``(MSB - MSW) / m0`` plus
    the within-subject ``MSW`` from a one-way ANOVA of the differences. CIs for
    bias and limits come from a participant-level (cluster) bootstrap.
    """
    d = df[[subject_col, ref_col, test_col]].dropna()
    if log_ratio:
        d = d[(d[ref_col] > 0) & (d[test_col] > 0)]
    diff = (
        np.log(d[test_col]) - np.log(d[ref_col])
        if log_ratio
        else d[test_col] - d[ref_col]
    )
    groups = [g.to_numpy(dtype=float) for _, g in diff.groupby(d[subject_col])]
    out: dict[str, Any] = {
        "n_subjects": len(groups),
        "n_windows": int(sum(len(g) for g in groups)),
        "log_ratio": log_ratio,
    }
    if len(groups) < 2:
        return out

    def _pooled(gs: list[np.ndarray]) -> tuple[float, float]:
        m = np.array([len(g) for g in gs], dtype=float)
        n_tot, k = m.sum(), len(gs)
        grand = np.concatenate(gs).mean()
        ssb = sum(len(g) * (g.mean() - grand) ** 2 for g in gs)
        ssw = sum(((g - g.mean()) ** 2).sum() for g in gs)
        msb = ssb / (k - 1)
        msw = ssw / (n_tot - k) if n_tot > k else 0.0
        m0 = (n_tot**2 - (m**2).sum()) / ((k - 1) * n_tot)
        var = max(msb - msw, 0.0) / m0 + msw
        return float(grand), float(np.sqrt(var))

    bias, sd = _pooled(groups)
    rng = np.random.default_rng(seed)
    boot = [
        _pooled([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        for _ in range(n_boot)
    ]
    b_bias = np.array([b for b, _ in boot])
    b_lo = np.array([b - 1.96 * s for b, s in boot])
    b_hi = np.array([b + 1.96 * s for b, s in boot])
    tf = (lambda v: float(np.exp(v))) if log_ratio else float
    out.update(
        {
            "bias": tf(bias),
            "bias_ci_low": tf(np.percentile(b_bias, 2.5)),
            "bias_ci_high": tf(np.percentile(b_bias, 97.5)),
            "sd_diff": sd,
            "loa_lower": tf(bias - 1.96 * sd),
            "loa_lower_ci_low": tf(np.percentile(b_lo, 2.5)),
            "loa_lower_ci_high": tf(np.percentile(b_lo, 97.5)),
            "loa_upper": tf(bias + 1.96 * sd),
            "loa_upper_ci_low": tf(np.percentile(b_hi, 2.5)),
            "loa_upper_ci_high": tf(np.percentile(b_hi, 97.5)),
        }
    )
    return out


def grade(metrics: dict[str, Any]) -> dict[str, str]:
    """Interpretation labels, only where a published standard exists.

    MAPE: ANSI/CTA-2065 (<= 10 % acceptable). CCC: McBride (2005) bands.
    ICC: Koo & Li (2016) bands. Bias, LoA and RMSSD have no universal
    threshold; judge them against the effect size your study needs to detect.
    """

    def band(v: Any, cuts: list[tuple[float, str]], below: str) -> str:
        if v is None or not np.isfinite(v):
            return "n/a"
        for cut, label in cuts:
            if v >= cut:
                return label
        return below

    mape = metrics.get("mape")
    return {
        "mape": "n/a"
        if mape is None or not np.isfinite(mape)
        else ("acceptable" if mape <= 10.0 else "not acceptable"),
        "lins_ccc": band(
            metrics.get("lins_ccc"),
            [(0.99, "almost perfect"), (0.95, "substantial"), (0.90, "moderate")],
            "poor",
        ),
        "icc_2_1": band(
            metrics.get("icc_2_1"),
            [(0.90, "excellent"), (0.75, "good"), (0.50, "moderate")],
            "poor",
        ),
    }


# (label, reference column, test column, artifact column, log-ratio LoA)
COMPARISONS: tuple[tuple[str, str, str, str | None, bool], ...] = (
    ("PPG HR (beats)", "ref_hr", "ppg_hr", "artifact", False),
    ("PPG HR (spectral)", "ref_hr", "ppg_hr_spectral", "artifact", False),
    ("PPG RMSSD", "ref_rmssd", "ppg_rmssd", "artifact", True),
    ("Sense PPI HR", "ref_hr", "ppi_hr", "ppi_artifact", False),
    ("Sense PPI RMSSD", "ref_rmssd", "ppi_rmssd", "ppi_artifact", True),
    ("Sense reported HR", "ref_hr", "sense_reported_hr", "artifact", False),
    ("H10 reported HR", "ref_hr", "h10_reported_hr", None, False),
)


def validate_windows(
    windows: pd.DataFrame, n_boot: int = N_BOOT
) -> list[dict[str, Any]]:
    """All comparisons for one session, on all windows and on artifact-free windows.

    Windows whose *reference* is incomplete (``ref_ok`` False) are dropped from
    both, since that criterion never looks at the test device. ``all`` is the
    primary result; ``clean`` is the sensitivity analysis.
    """
    if windows.empty:
        return []
    ok = windows[windows["ref_ok"]] if "ref_ok" in windows else windows
    results = []
    for label, ref_col, test_col, art_col, log_ratio in COMPARISONS:
        if test_col not in ok or ok[test_col].notna().sum() < 3:
            continue
        res: dict[str, Any] = {
            "label": label,
            "n_windows": len(windows),
            "n_ref_ok": len(ok),
            "all": agreement(
                ok[ref_col], ok[test_col], log_ratio=log_ratio, n_boot=n_boot
            ),
        }
        if art_col and art_col in ok:
            clean = ok[~ok[art_col].astype(bool)]
            res["n_artifact"] = int(ok[art_col].astype(bool).sum())
            res["clean"] = agreement(
                clean[ref_col], clean[test_col], log_ratio=log_ratio, n_boot=n_boot
            )
        for key in ("all", "clean"):
            if key in res and not log_ratio:
                res[key]["grades"] = grade(res[key])
        results.append(res)
    return results
