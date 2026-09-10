"""AudioEngine multi-track output cycle detection (setter-only)."""

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


def test_self_output_still_rejected(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    with pytest.raises(ValueError):
        engine.set_track_output(0, 0)
    assert engine.get_track_output(0) == "master"


def test_unknown_dest_still_valueerror(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    with pytest.raises(ValueError):
        engine.set_track_output(0, "bus1")
    with pytest.raises(ValueError):
        engine.set_track_output(0, "not_a_track")
    engine.set_track_output(0, "master")
    assert engine.get_track_output(0) == "master"
    engine.set_track_output(0, None)
    assert engine.get_track_output(0) == "master"


def test_acyclic_zero_to_one_silences_via_dest_fader(qapp):
    """set_track_output(0, 1) + dest volume 0 → master silent (slice 1)."""
    engine = AudioEngine(sample_rate=SR)
    n = SR
    engine.load_audio(0, _tone(n, 0.6))
    engine.set_track_output(0, 1)
    engine.set_track_volume(1, 0.0)
    assert engine.get_track_output(0) == 1
    mixed = engine.mix()
    _assert_stereo_float32(mixed)
    assert np.max(np.abs(mixed)) < 1e-6


def test_direct_two_cycle_rejected_graph_unchanged(qapp):
    """1→0 already set; set_track_output(0, 1) raises and 0 stays master."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.load_audio(1, _tone(64, 0.3))
    engine.set_track_output(1, 0)
    assert engine.get_track_output(1) == 0
    assert engine.get_track_output(0) == "master"
    with pytest.raises(ValueError, match="cycle"):
        engine.set_track_output(0, 1)
    assert engine.get_track_output(0) == "master"
    assert engine.get_track_output(1) == 0


def test_longer_cycle_rejected(qapp):
    """0→1, 1→2, then set_track_output(2, 0) raises; 2 stays master."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.load_audio(1, _tone(64, 0.2))
    engine.load_audio(2, _tone(64, 0.2))
    engine.set_track_output(0, 1)
    engine.set_track_output(1, 2)
    with pytest.raises(ValueError, match="cycle"):
        engine.set_track_output(2, 0)
    assert engine.get_track_output(0) == 1
    assert engine.get_track_output(1) == 2
    assert engine.get_track_output(2) == "master"


def test_acyclic_chain_allowed_follows_dest_faders(qapp):
    """0→1, 1→2, 2→master is OK; mix is still one-hop through dest faders."""
    engine = AudioEngine(sample_rate=SR)
    n = SR
    engine.load_audio(0, _tone(n, 0.4))
    engine.load_audio(1, _tone(n, 0.6))
    engine.set_track_output(0, 1)
    engine.set_track_output(1, 2)
    assert engine.get_track_output(0) == 1
    assert engine.get_track_output(1) == 2
    assert engine.get_track_output(2) == "master"

    # Track 1 one-hops into 2; dest fader 0 silences that hop (and 0→1
    # is not mixed to master because 1 is not dest=master).
    engine.set_track_volume(2, 0.0)
    silent = engine.mix()
    _assert_stereo_float32(silent)
    assert np.max(np.abs(silent)) < 1e-6

    engine.set_track_volume(2, 0.5)
    mixed = engine.mix()
    _assert_stereo_float32(mixed)
    expected = np.float32(np.tanh(0.6 * 0.5))
    assert np.allclose(mixed, expected, atol=1e-5)
