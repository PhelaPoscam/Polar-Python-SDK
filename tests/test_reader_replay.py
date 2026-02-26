"""Tests for replaying dataset rows through the Reader."""

from __future__ import annotations

import queue

import numpy as np
import pandas as pd

from awe_polar.connector.exporters.queue_sink import QueueSink
from awe_polar.connector.offline.dataset_loader import iter_csv
from awe_polar.reader.model_loader import ModelBundle
from awe_polar.reader.predictor import StressPredictor
from awe_polar.reader.realtime import run_reader


class DummyScaler:
    def transform(self, X):
        return X


class DummyModel:
    def predict_proba(self, X):
        return np.array([[0.2, 0.8] for _ in range(len(X))])


class LowStressModel:
    def predict_proba(self, X):
        return np.array([[0.55, 0.45] for _ in range(len(X))])


def test_replay_dataset_through_reader(tmp_path):
    data = pd.DataFrame(
        {
            "HR": [70, 75, 80],
            "RMSSD": [45.5, 42.2, 38.9],
        }
    )
    csv_path = tmp_path / "replay.csv"
    data.to_csv(csv_path, index=False)

    column_map = {
        "signals": {"hr_bpm": "HR"},
        "features": {"rmssd": "RMSSD"},
    }

    packets = list(iter_csv(csv_path, column_map, source="test"))

    q = queue.Queue()
    sink = QueueSink(q)
    for packet in packets:
        sink.send(packet)

    bundle = ModelBundle(model=DummyModel(), scaler=DummyScaler())
    predictor = StressPredictor(bundle, feature_order=["rmssd", "hr_bpm"])

    predictions = []

    def on_prediction(prediction):
        predictions.append(prediction)

    run_reader(predictor, q, on_prediction, stop_on_empty=True)

    assert len(predictions) == 3
    assert all(p.label == "High Stress" for p in predictions)
    assert all(np.isclose(p.confidence, 0.8) for p in predictions)


def test_replay_dataset_low_stress_label(tmp_path):
    data = pd.DataFrame(
        {
            "HR": [68, 72],
            "RMSSD": [55.0, 52.4],
        }
    )
    csv_path = tmp_path / "replay_low.csv"
    data.to_csv(csv_path, index=False)

    column_map = {
        "signals": {"hr_bpm": "HR"},
        "features": {"rmssd": "RMSSD"},
    }

    packets = list(iter_csv(csv_path, column_map, source="test"))

    q = queue.Queue()
    sink = QueueSink(q)
    for packet in packets:
        sink.send(packet)

    bundle = ModelBundle(model=LowStressModel(), scaler=DummyScaler())
    predictor = StressPredictor(bundle, feature_order=["rmssd", "hr_bpm"])

    predictions = []

    def on_prediction(prediction):
        predictions.append(prediction)

    run_reader(predictor, q, on_prediction, stop_on_empty=True)

    assert len(predictions) == 2
    assert all(p.label == "Low Stress" for p in predictions)
