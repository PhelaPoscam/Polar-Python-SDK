"""Stress prediction logic for standardized packets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from connector.schemas import SignalPacket
from .model_loader import ModelBundle


@dataclass(frozen=True)
class Prediction:
    label: str
    score: float
    confidence: float


class StressPredictor:
    """Predict stress state from connector packets."""

    def __init__(self, bundle: ModelBundle, feature_order: list[str] | None = None) -> None:
        self._bundle = bundle
        self._feature_order = feature_order or ["rmssd", "hr_bpm"]

    def predict(self, packet: SignalPacket | dict[str, Any]) -> Prediction:
        if isinstance(packet, SignalPacket):
            payload = packet.to_dict()
        else:
            payload = packet

        features = payload.get("features") or {}
        signals = payload.get("signals") or {}

        values = []
        for key in self._feature_order:
            if key in features:
                values.append(features[key])
            elif key in signals:
                values.append(signals[key])
            else:
                values.append(0.0)

        X = np.asarray(values, dtype=float).reshape(1, -1)
        X_scaled = self._bundle.scaler.transform(X)

        if hasattr(self._bundle.model, "predict_proba"):
            proba = self._bundle.model.predict_proba(X_scaled)[0]
            score = float(proba[1]) if len(proba) > 1 else float(proba[0])
            pred_idx = int(np.argmax(proba))
            confidence = float(proba[pred_idx])
        else:
            score = float(self._bundle.model.predict(X_scaled)[0])
            confidence = 1.0
            pred_idx = 1 if score >= 0.5 else 0

        label = "High Stress" if pred_idx == 1 else "Baseline"
        if 0.35 <= score <= 0.65:
            label = "Low Stress"

        return Prediction(label=label, score=score, confidence=confidence)
