"""Model loading utilities for the Reader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib


@dataclass(frozen=True)
class ModelBundle:
    model: object
    scaler: object


def load_model_bundle(model_path: Path | str, scaler_path: Path | str) -> ModelBundle:
    """Load model and scaler artifacts from disk."""
    model = joblib.load(Path(model_path))
    scaler = joblib.load(Path(scaler_path))
    return ModelBundle(model=model, scaler=scaler)
