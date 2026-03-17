from datetime import datetime, timedelta

from awe_polar.ring_device.mm_compat import (
    DEFAULT_OHMS_PER_RAW_UNIT,
    MMFeatures,
    MMLikeScorer,
    decode_raw_resistance_packet,
    decode_streaming_packet,
)


def test_decode_streaming_packet_basic():
    packet = bytes([3, 45, 64, 0, 170, 160, 164])
    decoded = decode_streaming_packet(packet)

    assert decoded is not None
    assert decoded["status_bits"]["MM_not_ready"] == 1
    assert decoded["status_bits"]["ring_in_finger"] == 1
    assert decoded["mm_number"] == 45
    assert decoded["instant_eda"] == 16384
    assert abs(decoded["ax_g"] - (170 / 255)) < 1e-6
    assert abs(decoded["ay_g"] - (160 / 255)) < 1e-6
    assert abs(decoded["az_g"] - (164 / 255)) < 1e-6
    assert 1.0 < decoded["accel_magnitude_g"] < 1.2


def test_decode_raw_resistance_packet_basic():
    packet = bytes([13, 136])
    decoded = decode_raw_resistance_packet(packet)

    assert decoded is not None
    assert decoded["raw_skin_resistance_value"] == 3464
    assert abs(decoded["skin_resistance_ohms"] - 845716.029603) < 0.001
    assert abs(decoded["skin_conductance_microsiemens"] - 1.18243) < 0.0001


def test_decode_raw_resistance_packet_custom_scale():
    packet = bytes([0x00, 0x64])
    decoded = decode_raw_resistance_packet(packet, ohms_per_raw_unit=10.0)

    assert decoded is not None
    assert decoded["raw_skin_resistance_value"] == 100
    assert decoded["skin_resistance_ohms"] == 1000.0
    assert decoded["skin_conductance_microsiemens"] == 1000.0


def test_mm_like_scorer_calibrates_and_scales():
    scorer = MMLikeScorer(calibration_seconds=10)
    t0 = datetime.now()

    low = MMFeatures(scr_frequency_per_min=0.0, scr_amplitude=0.0, scl_microsiemens=0.5)
    high = MMFeatures(
        scr_frequency_per_min=8.0, scr_amplitude=5.0, scl_microsiemens=3.0
    )

    state0 = scorer.update(low, now=t0)
    state1 = scorer.update(high, now=t0 + timedelta(seconds=5))
    state2 = scorer.update(high, now=t0 + timedelta(seconds=11))

    assert state0["calibrated"] is False
    assert state1["calibrated"] is False
    assert state2["calibrated"] is True
    assert 1.0 <= state2["mm_like_1_to_100"] <= 100.0


def test_mm_like_scr_event_frequency_tracking():
    scorer = MMLikeScorer(calibration_seconds=10)
    t0 = datetime.now()

    # Prime baseline
    scorer.update_scr_features(tonic_value=10.0, now=t0)

    # First event
    freq1, amp1 = scorer.update_scr_features(
        tonic_value=20.0, now=t0 + timedelta(seconds=4)
    )
    # Refractory, should not increase count
    freq2, amp2 = scorer.update_scr_features(
        tonic_value=21.0, now=t0 + timedelta(seconds=5)
    )
    # Next valid event
    freq3, amp3 = scorer.update_scr_features(
        tonic_value=22.0, now=t0 + timedelta(seconds=8)
    )

    assert amp1 > 0
    assert amp2 > 0
    assert amp3 > 0
    assert freq1 == 1.0
    assert freq2 == 1.0
    assert freq3 == 2.0


def test_default_ohms_constant_nonzero():
    assert DEFAULT_OHMS_PER_RAW_UNIT > 0
