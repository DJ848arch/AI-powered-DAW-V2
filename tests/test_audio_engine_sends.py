"""AudioEngine M1 per-track sends (mix path only). Engine-only, no UI."""

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


def test_send_path_is_extra_not_replacement(qapp):
    """Track 0 → master + send to bus fx: both paths on master (more energy)."""
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
    assert engine.get_sends(0) == ["fx"]
    with_send = engine.mix()
    _assert_stereo_float32(with_send)
    # Direct + bus copy of the same post-fader audio, then master tanh.
    expected_both = np.float32(np.tanh(amp + amp))
    assert np.allclose(with_send, expected_both, atol=1e-5)
    assert _rms(with_send) > _rms(without)
    # Main dest is still master — send did not replace it.
    assert engine.get_track_output(0) == "master"


def test_main_output_independent_of_send(qapp):
    """0→1 silenced by dest fader; send to bus still appears. Inverse silent."""
    engine = AudioEngine(sample_rate=SR)
    n = SR
    amp = 0.5
    engine.load_audio(0, _tone(n, amp))
    engine.set_track_output(0, 1)
    engine.set_track_volume(1, 0.0)

    # Inverse / regression: no send, dest fader 0 → master silent.
    silent = engine.mix()
    _assert_stereo_float32(silent)
    assert np.max(np.abs(silent)) < 1e-6

    engine.add_bus("fx")
    engine.add_send(0, "fx")
    mixed = engine.mix()
    _assert_stereo_float32(mixed)
    # Direct 0→1 is silenced; send copy still goes through the bus to master.
    expected = np.float32(np.tanh(amp))
    assert np.allclose(mixed, expected, atol=1e-5)
    assert np.max(np.abs(mixed)) > 1e-4


def test_unknown_send_dest_rejected_graph_unchanged(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.add_bus("fx")
    engine.add_send(0, "fx")
    before_sends = engine.get_sends(0)
    before_out = engine.get_track_output(0)
    before_mix = engine.mix().copy()

    with pytest.raises(ValueError):
        engine.add_send(0, "ghost")
    with pytest.raises(ValueError):
        engine.add_send(0, 99)

    assert engine.get_sends(0) == before_sends
    assert engine.get_track_output(0) == before_out
    after = engine.mix()
    assert np.allclose(after, before_mix, atol=1e-6)


def test_send_to_master_rejected(qapp):
    """Main output already covers master; a send to master would double."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    with pytest.raises(ValueError):
        engine.add_send(0, "master")
    with pytest.raises(ValueError):
        engine.add_send(0, "Master")
    assert engine.get_sends(0) == []
    mixed = engine.mix()
    expected = np.float32(np.tanh(0.2))
    assert np.allclose(mixed, expected, atol=1e-5)


def test_self_send_rejected_and_duplicate_idempotent(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, 0.3))
    engine.load_audio(1, _tone(SR, 0.0))
    with pytest.raises(ValueError):
        engine.add_send(0, 0)
    assert engine.get_sends(0) == []

    engine.add_bus("drum")
    engine.add_send(0, "drum")
    engine.add_send(0, "drum")
    assert engine.get_sends(0) == ["drum"]
    mixed = engine.mix()
    # One extra copy, not two: tanh(0.3 direct + 0.3 send). Track 1 is silence.
    expected = np.float32(np.tanh(0.3 + 0.3))
    assert np.allclose(mixed, expected, atol=1e-5)


def test_track_to_track_main_plus_bus_send(qapp):
    """0→1 and send 0→drum: appears through dest 1 fader AND bus to master."""
    engine = AudioEngine(sample_rate=SR)
    n = SR
    engine.load_audio(0, _tone(n, 0.4))
    engine.set_track_output(0, 1)
    engine.set_track_volume(1, 0.5)
    engine.add_bus("drum")
    engine.add_send(0, "drum")
    mixed = engine.mix()
    _assert_stereo_float32(mixed)
    # Main: raw 0.4 through dest fader 0.5 = 0.2; send: post-fader 0.4 to bus.
    expected = np.float32(np.tanh(0.4 * 0.5 + 0.4))
    assert np.allclose(mixed, expected, atol=1e-5)


def test_sends_not_persisted_in_get_state(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.add_bus("fx")
    engine.add_send(0, "fx")
    state = engine.get_state()
    assert "sends" not in state
    assert "track_sends" not in state
    # Mix still uses in-memory sends without requiring them in state.
    mixed = engine.mix()
    expected = np.float32(np.tanh(0.2 + 0.2))
    assert np.allclose(mixed, expected, atol=1e-5)


def test_unload_and_clear_drop_sends(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.load_audio(1, _tone(64, 0.3))
    engine.add_bus("fx")
    engine.add_send(0, "fx")
    engine.add_send(0, 1)
    engine.add_send(1, "fx")
    engine.unload_track(0)
    assert engine.get_sends(0) == []
    assert 1 not in engine.get_sends(1)
    engine.clear()
    assert engine.get_sends(0) == []
    assert engine.get_sends(1) == []
    assert engine.track_sends == {}


def test_remove_send_stops_extra_path(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, 0.4))
    engine.add_bus("fx")
    engine.add_send(0, "fx")
    engine.remove_send(0, "fx")
    assert engine.get_sends(0) == []
    mixed = engine.mix()
    expected = np.float32(np.tanh(0.4))
    assert np.allclose(mixed, expected, atol=1e-5)
