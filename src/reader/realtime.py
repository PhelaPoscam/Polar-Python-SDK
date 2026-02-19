"""Live reader loop for queue-based packets."""

from __future__ import annotations

import queue
from dataclasses import dataclass
from time import sleep
from typing import Callable, Iterator

from connector.schemas import SignalPacket
from .predictor import Prediction, StressPredictor


@dataclass
class ReaderConfig:
    poll_interval: float = 0.05


def iter_queue(
    source: queue.Queue,
    stop_on_empty: bool = False,
    config: ReaderConfig | None = None,
) -> Iterator[SignalPacket | dict]:
    """Yield packets from a Queue with optional idle polling."""
    cfg = config or ReaderConfig()
    while True:
        try:
            packet = source.get(timeout=cfg.poll_interval)
        except queue.Empty:
            if stop_on_empty:
                break
            sleep(cfg.poll_interval)
            continue
        yield packet


def run_reader(
    predictor: StressPredictor,
    source: queue.Queue,
    on_prediction: Callable[[Prediction], None],
    config: ReaderConfig | None = None,
    stop_on_empty: bool = False,
) -> None:
    """Run a live reader loop that consumes queue packets."""
    for packet in iter_queue(source, stop_on_empty=stop_on_empty, config=config):
        prediction = predictor.predict(packet)
        on_prediction(prediction)
