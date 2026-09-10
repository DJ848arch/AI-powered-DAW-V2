"""AudioEngine track-output routing (slice 1). Engine-only, no MainWindow."""

import numpy as np
import pytest

from audio_engine import AudioEngine
from midi_synth import render_midi


SR = 8000


def _tone(n, value=0.5):
    return np.full((n, 2), value, dtype=np.float32)


def _assert_stereo_float32(mix):
    assert isinstance(mix, np.ndarray)
    assert mix.dtype == np.float32
    assert mix.ndim == 2
    assert mix.shape[1] == 2


def test_default_two_tones_both_appear_on_master(qapp):
    """Regression: dest missing/'master' is today's mix — both tracks on master."""
    engine = AudioEngine(sample_rate=SR)
    n = SR
    engine.load_audio(0, _tone(n, 0.3))
    engine.load_audio(1, _tone(n, 0.4))
    assert engine.get_track_output(0) == "master"
    assert engine.get_track_output(1) == "master"
    mixed = engine.mix()
    _assert_stereo_float32(mixed)
    expected = np.float32(np.tanh(0.3 + 0.4))
    assert np.allclose(mixed, expected, atol=1e-5)
    # Independent to master: silencing track 1 still leaves track 0.
    engine.set_track_volume(1, 0.0)
    mixed_one = engine.mix()
    expected_one = np.float32(np.tanh(0.3))
    assert np.allclose(mixed_one, expected_one, atol=1e-5)


def test_route_to_dest_volume_zero_silences_master(qapp):
    """set_track_output(0, 1) + dest volume 0 → master silent (0 only through 1)."""
    engine = AudioEngine(sample_rate=SR)
    n = SR
    engine.load_audio(0, _tone(n, 0.6))
    engine.set_track_output(0, 1)
    engine.set_track_volume(1, 0.0)
    assert engine.get_track_output(0) == 1
    mixed = engine.mix()
    _assert_stereo_float32(mixed)
    assert np.max(np.abs(mixed)) < 1e-6


def test_route_to_dest_volume_half_scales_through_fader(qapp):
    """Track 0 at 1.0 routed to 1 at 0.5 → tone at ~0.5, then tanh limiter."""
    engine = AudioEngine(sample_rate=SR)
    n = SR
    amp = 1.0
    engine.load_audio(0, _tone(n, amp))
    engine.set_track_volume(0, 1.0)
    engine.set_track_output(0, 1)
    engine.set_track_volume(1, 0.5)
    mixed = engine.mix()
    _assert_stereo_float32(mixed)
    # Dest fader 0.5 applies to routed-in audio before the master tanh.
    expected = np.float32(np.tanh(amp * 0.5))
    assert np.allclose(mixed, expected, atol=1e-5)


def test_wav_ndarray_and_render_midi_both_follow_dest(qapp):
    """WAV ndarray + render_midi buffer load_audio'd on track 0 both follow dest=1."""
    engine = AudioEngine(sample_rate=SR)
    wav = _tone(SR // 2, 0.4)
    midi_buf = render_midi(
        notes=[{
            "pitch": 60,
            "start_beat": 0.0,
            "duration_beats": 1.0,
            "velocity": 100,
        }],
        instrument="piano",
        bpm=120,
        sample_rate=SR,
    )
    assert midi_buf.ndim == 2 and midi_buf.shape[1] == 2
    assert np.max(np.abs(wav)) > 1e-4
    assert np.max(np.abs(midi_buf)) > 1e-4

    engine.load_audio(0, wav)
    engine.load_audio(0, midi_buf)
    engine.set_track_output(0, 1)

    n = max(len(wav), len(midi_buf))
    summed = np.zeros((n, 2), dtype=np.float32)
    summed[: len(wav)] += wav
    summed[: len(midi_buf)] += midi_buf

    engine.set_track_volume(1, 0.0)
    silent = engine.mix()
    _assert_stereo_float32(silent)
    assert np.max(np.abs(silent)) < 1e-6

    engine.set_track_volume(1, 1.0)
    full = engine.mix()
    _assert_stereo_float32(full)
    assert full.shape[0] == n
    expected_full = np.tanh(summed).astype(np.float32)
    assert np.allclose(full, expected_full, atol=1e-4)
    assert np.max(np.abs(full)) > 1e-4

    engine.set_track_volume(1, 0.5)
    half = engine.mix()
    expected_half = np.tanh(summed * 0.5).astype(np.float32)
    assert np.allclose(half, expected_half, atol=1e-4)


def test_set_track_output_rejects_unknown_dest(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    with pytest.raises(ValueError):
        engine.set_track_output(0, "bus1")
    with pytest.raises(ValueError):
        engine.set_track_output(0, "not_a_track")
    with pytest.raises(ValueError):
        engine.set_track_output(0, 0)  # self-output
    engine.set_track_output(0, "master")
    assert engine.get_track_output(0) == "master"
    engine.set_track_output(0, None)
    assert engine.get_track_output(0) == "master"

    # Persist round-trip
    engine.set_track_output(0, 1)
    state = engine.get_state()
    assert "track_outputs" in state
    other = AudioEngine(sample_rate=SR)
    other.set_state(state)
    assert other.get_track_output(0) == 1
