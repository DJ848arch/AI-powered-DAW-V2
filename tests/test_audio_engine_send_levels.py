"""AudioEngine per-send levels (post-fader extra copies). Engine-only, no UI."""

import math

import numpy as np
import pytest

from audio_engine import AudioEngine


SR = 8000


def _tone(n, value=0.5):
    return np.full((n, 2), value, dtype=np.float32)


def _assert_stereo_float32(mix):
    assert isinstance(mix, np.ndarray)
    assert mix.dtype == np.float32
    assert mix.ndim == 2
    assert mix.shape[1] == 2


def _rms(mix):
    return float(np.sqrt(np.mean(np.square(mix, dtype=np.float64))))


def test_send_level_finite_non_negative_validation(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.add_bus("fx")

    with pytest.raises(ValueError):
        engine.add_send(0, "fx", level=-0.1)
    assert engine.get_sends(0) == []

    engine.add_send(0, "fx", level=1.0)
    assert engine.get_send_level(0, "fx") == 1.0

    for bad in (-1.0, float("inf"), float("-inf"), float("nan"), math.nan, np.inf, np.nan):
        with pytest.raises(ValueError):
            engine.set_send_level(0, "fx", bad)
        got = engine.get_send_level(0, "fx")
        assert got == 1.0
        assert math.isfinite(got)

    engine.set_send_level(0, "fx", 0.0)
    assert engine.get_send_level(0, "fx") == 0.0
    engine.set_send_level(0, "fx", 1.0)
    assert engine.get_send_level(0, "fx") == 1.0

    engine.add_bus("drum")
    engine.add_send(0, "drum", level=0.0)
    assert engine.get_send_level(0, "drum") == 0.0

    with pytest.raises(ValueError):
        engine.set_send_level(0, "ghost", 0.5)
    with pytest.raises(ValueError):
        engine.get_send_level(0, "ghost")
    engine.add_bus("verb")
    with pytest.raises(ValueError):
        engine.set_send_level(0, "verb", 0.5)
    with pytest.raises(ValueError):
        engine.get_send_level(0, "verb")


def test_send_level_zero_silences_only_send(qapp):
    """Level 0: send to fx silenced; master equals no-send (main still there)."""
    engine = AudioEngine(sample_rate=SR)
    n = SR
    amp = 0.4
    engine.load_audio(0, _tone(n, amp))
    without = engine.mix()
    _assert_stereo_float32(without)
    expected_direct = np.float32(np.tanh(amp))
    assert np.allclose(without, expected_direct, atol=1e-5)

    engine.add_bus("fx")
    engine.add_send(0, "fx")
    engine.set_send_level(0, "fx", 0.0)
    assert engine.get_send_level(0, "fx") == 0.0
    assert engine.get_sends(0) == ["fx"]
    assert engine.get_track_output(0) == "master"

    silenced = engine.mix()
    _assert_stereo_float32(silenced)
    assert np.allclose(silenced, without, atol=1e-6)
    assert np.allclose(silenced, expected_direct, atol=1e-5)
    assert np.max(np.abs(silenced)) > 1e-4


def test_send_level_unity_matches_implicit_full_copy(qapp):
    """Unity (1.0) preserves first-slice extra-send energy (implicit 1.0)."""
    amp = 0.4
    n = SR

    implicit = AudioEngine(sample_rate=SR)
    implicit.load_audio(0, _tone(n, amp))
    implicit.add_bus("fx")
    implicit.add_send(0, "fx")
    assert implicit.get_send_level(0, "fx") == 1.0
    mix_implicit = implicit.mix()

    explicit_add = AudioEngine(sample_rate=SR)
    explicit_add.load_audio(0, _tone(n, amp))
    explicit_add.add_bus("fx")
    explicit_add.add_send(0, "fx", level=1.0)
    mix_add = explicit_add.mix()

    via_setter = AudioEngine(sample_rate=SR)
    via_setter.load_audio(0, _tone(n, amp))
    via_setter.add_bus("fx")
    via_setter.add_send(0, "fx")
    via_setter.set_send_level(0, "fx", 1.0)
    mix_set = via_setter.mix()

    expected = np.float32(np.tanh(amp + amp))
    for mixed in (mix_implicit, mix_add, mix_set):
        _assert_stereo_float32(mixed)
        assert np.allclose(mixed, expected, atol=1e-5)
    assert np.allclose(mix_implicit, mix_add, atol=1e-6)
    assert np.allclose(mix_implicit, mix_set, atol=1e-6)
    assert _rms(mix_implicit) > _rms(np.tanh(np.full((n, 2), amp, dtype=np.float32)))


def test_send_follows_source_fader_then_send_level(qapp):
    """Post-fader then send level. Volume 0 silences both; vol 1 + send 0 = main only."""
    engine = AudioEngine(sample_rate=SR)
    n = SR
    amp = 0.5
    engine.load_audio(0, _tone(n, amp))
    engine.add_bus("fx")
    engine.add_send(0, "fx", level=1.0)

    engine.set_track_volume(0, 0.0)
    silent = engine.mix()
    _assert_stereo_float32(silent)
    assert np.max(np.abs(silent)) < 1e-6

    engine.set_track_volume(0, 1.0)
    engine.set_send_level(0, "fx", 0.0)
    main_only = engine.mix()
    expected_main = np.float32(np.tanh(amp))
    assert np.allclose(main_only, expected_main, atol=1e-5)
    assert np.max(np.abs(main_only)) > 1e-4

    engine.set_send_level(0, "fx", 1.0)
    engine.set_track_volume(0, 0.5)
    half = engine.mix()
    # Post-fader 0.5 then send unity: direct 0.25 + send 0.25.
    expected_half = np.float32(np.tanh(amp * 0.5 + amp * 0.5))
    assert np.allclose(half, expected_half, atol=1e-5)


def test_main_output_unchanged_when_send_level_unity(qapp):
    """0→1 dest vol 0 + send to bus at 1: send on master; dest vol 0 silences 0→1."""
    engine = AudioEngine(sample_rate=SR)
    n = SR
    amp = 0.5
    engine.load_audio(0, _tone(n, amp))
    engine.set_track_output(0, 1)
    engine.set_track_volume(1, 0.0)

    silent = engine.mix()
    _assert_stereo_float32(silent)
    assert np.max(np.abs(silent)) < 1e-6

    engine.add_bus("fx")
    engine.add_send(0, "fx", level=1.0)
    mixed = engine.mix()
    _assert_stereo_float32(mixed)
    expected = np.float32(np.tanh(amp))
    assert np.allclose(mixed, expected, atol=1e-5)
    assert np.max(np.abs(mixed)) > 1e-4

    engine.set_send_level(0, "fx", 0.0)
    both_silent = engine.mix()
    assert np.max(np.abs(both_silent)) < 1e-6


def test_sends_and_levels_not_in_get_state(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.add_bus("fx")
    engine.add_send(0, "fx", level=0.5)
    state = engine.get_state()
    assert "sends" not in state
    assert "track_sends" not in state
    assert "track_send_levels" not in state
    assert "send_levels" not in state
