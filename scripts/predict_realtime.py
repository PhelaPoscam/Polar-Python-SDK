"""
Realtime prediction stub for TabNet stress model.

Usage:
  python scripts/predict_realtime.py --window-csv path/to/window.csv

The CSV should contain two columns: eda, hr (one sample per row).
"""

import argparse
import os

import joblib
import numpy as np
import pandas as pd
from pytorch_tabnet.tab_model import TabNetClassifier


def extract_features(eda_signal: np.ndarray, hr_signal: np.ndarray) -> np.ndarray:
    def stats(x: np.ndarray) -> list:
        mean = np.mean(x)
        median = np.median(x)
        std = np.std(x)
        var = np.var(x)
        min_v = np.min(x)
        max_v = np.max(x)
        skew = pd.Series(x).skew()
        kurt = pd.Series(x).kurt()
        dyn_range = max_v - min_v
        return [mean, median, std, var, min_v, max_v, skew, kurt, dyn_range]

    eda_feats = stats(eda_signal)
    hr_feats = stats(hr_signal)

    cov = np.cov(eda_signal, hr_signal)[0, 1]
    skin_resistance = np.mean(1.0 / (eda_signal + 1e-6))
    hrv = np.std(hr_signal)

    features = np.array(eda_feats + hr_feats + [cov, skin_resistance, hrv], dtype=np.float32)
    return np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Predict stress from a single EDA/HR window.")
    parser.add_argument("--window-csv", required=True, help="CSV with columns: eda, hr")
    parser.add_argument("--model-path", default=os.path.join("models", "tabnet_stress_model"), help="Model path (without .zip)")
    parser.add_argument("--scaler-path", default=os.path.join("models", "tabnet_stress_scaler.joblib"), help="Scaler joblib path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not os.path.isfile(args.window_csv):
        raise FileNotFoundError(f"Window CSV not found: {args.window_csv}")

    df = pd.read_csv(args.window_csv)
    if not {"eda", "hr"}.issubset(df.columns):
        raise ValueError("CSV must include 'eda' and 'hr' columns.")

    eda = df["eda"].to_numpy(dtype=np.float32)
    hr = df["hr"].to_numpy(dtype=np.float32)

    features = extract_features(eda, hr).reshape(1, -1)

    scaler = joblib.load(args.scaler_path)
    features = scaler.transform(features)

    model = TabNetClassifier()
    model.load_model(args.model_path)

    proba = model.predict_proba(features)[0]
    pred = int(np.argmax(proba))

    label = "Stress" if pred == 1 else "Non-Stress"
    print(f"Prediction: {label} | proba={proba}")


if __name__ == "__main__":
    main()
