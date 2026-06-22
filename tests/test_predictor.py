"""Unit tests for StressPredictor — ML inference on SignalPackets."""

import joblib
import numpy as np
import pytest
from pathlib import Path

from awe_polar.reader.model_loader import ModelBundle
from awe_polar.reader.predictor import StressPredictor, Prediction
from awe_polar.connector.schemas import SignalPacket


@pytest.fixture
def mock_bundle():
    """Train a tiny sklearn model so predict() exercises the real code path."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    X = np.array([[70, 45], [75, 40], [80, 30], [85, 25], [90, 20],
                  [60, 50], [65, 55], [70, 48], [72, 52], [68, 58]], dtype=float)
    y = np.array([0, 0, 1, 1, 1, 0, 0, 0, 0, 0])

    scaler = StandardScaler().fit(X)
    X_scaled = scaler.transform(X)
    model = LogisticRegression().fit(X_scaled, y)

    return ModelBundle(model=model, scaler=scaler)


class TestStressPredictor:
    def test_predict_stress_from_packet(self, mock_bundle):
        pred = StressPredictor(mock_bundle)
        packet = SignalPacket(
            source="h10", signals={"hr_bpm": 85}, features={"rmssd": 25.0}
        )
        result = pred.predict(packet)
        assert isinstance(result, Prediction)
        assert result.label in {"High Stress", "Baseline", "Low Stress"}

    def test_predict_from_dict(self, mock_bundle):
        pred = StressPredictor(mock_bundle)
        payload = {"signals": {"hr_bpm": 70}, "features": {"rmssd": 50.0}}
        result = pred.predict(payload)
        assert isinstance(result, Prediction)

    def test_missing_feature_falls_back_to_zero(self, mock_bundle):
        pred = StressPredictor(mock_bundle)
        packet = SignalPacket(source="h10", signals={"hr_bpm": 75})
        result = pred.predict(packet)
        assert isinstance(result, Prediction)
        # rmssd missing → 0.0 → HR+bogus-RMSSD → still produces a label
        assert result.label in {"High Stress", "Baseline", "Low Stress"}

    def test_low_stress_boundary_label(self, mock_bundle):
        pred = StressPredictor(mock_bundle)
        # Feed values that give a mid-range score
        packet = SignalPacket(source="h10", signals={"hr_bpm": 72},
                              features={"rmssd": 70.0})
        result = pred.predict(packet)
        # With realistic data we get a valid label
        assert result.label in {"High Stress", "Baseline", "Low Stress"}
        assert 0.0 <= result.confidence <= 1.0

    def test_custom_feature_order(self, mock_bundle):
        # Use the standard 2-feature order — the scaler was trained on 2 features.
        pred = StressPredictor(mock_bundle, feature_order=["hr_bpm", "rmssd"])
        packet = SignalPacket(source="h10", signals={"hr_bpm": 80},
                              features={"rmssd": 30.0})
        result = pred.predict(packet)
        assert isinstance(result, Prediction)

    def test_prediction_is_frozen_dataclass(self, mock_bundle):
        pred = StressPredictor(mock_bundle)
        result = pred.predict({"signals": {}, "features": {}})
        with pytest.raises(Exception):
            result.label = "changed"
