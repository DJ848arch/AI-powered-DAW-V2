"""AudioEngine named-bus mix destinations (mix path only). Engine-only, no UI."""

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


def test_add_bus_route_tone_appears_on_master(qapp):
    """add_bus('drum'); set_track_output(0, 'drum'); tone on 0 appears on master."""
    engine = AudioEngine(sample_rate=SR)
    n = SR
    engine.load_audio(0, _tone(n, 0.4))
    engine.add_bus("drum")
    assert "drum" in engine.list_buses()
    assert "drum" in engine.get_buses()
    engine.set_track_output(0, "drum")
    assert engine.get_track_output(0) == "drum"
    mixed = engine.mix()
    _assert_stereo_float32(mixed)
    expected = np.float32(np.tanh(0.4))
    assert np.allclose(mixed, expected, atol=1e-5)
    # Source fader applies before the bus (bus has no fader).
    engine.set_track_volume(0, 0.5)
    half = engine.mix()
    expected_half = np.float32(np.tanh(0.4 * 0.5))
    assert np.allclose(half, expected_half, atol=1e-5)


def test_bus_path_plus_direct_path_both_appear(qapp):
    """Track 0→drum and track 1→master: both tones appear on master."""
    engine = AudioEngine(sample_rate=SR)
    n = SR
    engine.load_audio(0, _tone(n, 0.3))
    engine.load_audio(1, _tone(n, 0.4))
    engine.add_bus("drum")
    engine.set_track_output(0, "drum")
    assert engine.get_track_output(1) == "master"
    mixed = engine.mix()
    _assert_stereo_float32(mixed)
    expected = np.float32(np.tanh(0.3 + 0.4))
    assert np.allclose(mixed, expected, atol=1e-5)


def test_mute_track_routed_to_bus_silences_that_tone(qapp):
    """Mute track 0 (0→drum): master loses that tone (still through the bus)."""
    engine = AudioEngine(sample_rate=SR)
    n = SR
    engine.load_audio(0, _tone(n, 0.5))
    engine.add_bus("drum")
    engine.set_track_output(0, "drum")
    engine.set_track_mute(0, True)
    silent = engine.mix()
    _assert_stereo_float32(silent)
    assert np.max(np.abs(silent)) < 1e-6

    engine.set_track_mute(0, False)
    engine.load_audio(1, _tone(n, 0.3))
    engine.set_track_mute(0, True)
    # Track 1 still direct to master
    mixed = engine.mix()
    expected = np.float32(np.tanh(0.3))
    assert np.allclose(mixed, expected, atol=1e-5)


def test_unknown_bus_dest_raises_valueerror(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    with pytest.raises(ValueError):
        engine.set_track_output(0, "no_such_bus")
    assert engine.get_track_output(0) == "master"


def test_buses_not_persisted_in_get_state(qapp):
    """Mix-graph only: bus definitions are not a get_state field."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.add_bus("drum")
    engine.set_track_output(0, "drum")
    state = engine.get_state()
    assert "buses" not in state
    assert "_buses" not in state
    # dest string may already live in track_outputs; that is ok
    assert state["track_outputs"][0] == "drum"


def test_track_to_bus_to_master_is_acyclic(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.add_bus("drum")
    engine.set_track_output(0, "drum")
    assert engine.validate_graph() is None
