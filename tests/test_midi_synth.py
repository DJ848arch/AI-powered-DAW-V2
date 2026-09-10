"""Acceptance tests for midi_synth.render_midi.

Skips until Engine lands src/midi_synth.py. Does not edit product code.
"""

import inspect

import numpy as np
import pytest

midi_synth = pytest.importorskip("midi_synth")


def _render_fn():
    if hasattr(midi_synth, "render_midi"):
        return midi_synth.render_midi
    synth_cls = getattr(midi_synth, "MidiSynth", None)
    if synth_cls is not None:
        return synth_cls().render_midi
    pytest.fail("midi_synth.render_midi is missing")


def _call_render(
    *,
    pitch=60,
    start_beat=0,
    duration_beats=1,
    velocity=100,
    bpm=120,
    instrument="piano",
    sample_rate=8000,
):
    """Call render_midi with either a flat kwargs API or a notes= list."""
    fn = _render_fn()
    params = inspect.signature(fn).parameters
    names = set(params)

    def _accepts(name):
        return name in names or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())

    if "notes" in names and "pitch" not in names:
        note = {
            "pitch": pitch,
            "start_beat": start_beat,
            "duration_beats": duration_beats,
            "velocity": velocity,
        }
        kwargs = {"notes": [note], "bpm": bpm, "instrument": instrument}
        if _accepts("sample_rate"):
            kwargs["sample_rate"] = sample_rate
        return fn(**kwargs)

    kwargs = {
        "pitch": pitch,
        "start_beat": start_beat,
        "duration_beats": duration_beats,
        "velocity": velocity,
        "bpm": bpm,
        "instrument": instrument,
    }
    if _accepts("sample_rate"):
        kwargs["sample_rate"] = sample_rate
    # Drop names the function does not take (unless **kwargs).
    if not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        kwargs = {k: v for k, v in kwargs.items() if k in names}
    return fn(**kwargs)


def _assert_stereo_float32(audio):
    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert audio.ndim == 2
    assert audio.shape[1] == 2


def test_c4_one_beat_at_120_is_nonsilent_stereo_float32():
    audio = _call_render(pitch=60, start_beat=0, duration_beats=1, velocity=100, bpm=120)
    _assert_stereo_float32(audio)
    assert audio.shape[0] > 0
    assert np.max(np.abs(audio)) > 1e-4


def test_start_beat_1_is_silent_before_that_beat():
    bpm = 120
    sr = 8000
    audio = _call_render(
        pitch=60, start_beat=1, duration_beats=1, velocity=100, bpm=bpm, sample_rate=sr
    )
    _assert_stereo_float32(audio)
    # 120 bpm => 0.5s per beat
    silent_n = int(round(0.5 * sr))
    assert audio.shape[0] > silent_n
    assert np.max(np.abs(audio[:silent_n])) < 1e-5
    assert np.max(np.abs(audio[silent_n:])) > 1e-4


def test_duration_beats_affects_length():
    one = _call_render(pitch=60, duration_beats=1, bpm=120, sample_rate=8000)
    two = _call_render(pitch=60, duration_beats=2, bpm=120, sample_rate=8000)
    _assert_stereo_float32(one)
    _assert_stereo_float32(two)
    assert two.shape[0] > one.shape[0]


def test_velocity_20_vs_100_changes_amplitude():
    quiet = _call_render(pitch=60, duration_beats=1, velocity=20, bpm=120)
    loud = _call_render(pitch=60, duration_beats=1, velocity=100, bpm=120)
    _assert_stereo_float32(quiet)
    _assert_stereo_float32(loud)
    assert np.max(np.abs(loud)) > np.max(np.abs(quiet))


def test_piano_drums_bass_are_not_identical():
    kwargs = dict(pitch=60, duration_beats=1, velocity=100, bpm=120, sample_rate=8000)
    piano = _call_render(instrument="piano", **kwargs)
    drums = _call_render(instrument="drums", **kwargs)
    bass = _call_render(instrument="bass", **kwargs)
    for audio in (piano, drums, bass):
        _assert_stereo_float32(audio)
    n = min(len(piano), len(drums), len(bass))
    assert not np.allclose(piano[:n], drums[:n], atol=1e-5)
    assert not np.allclose(piano[:n], bass[:n], atol=1e-5)
    assert not np.allclose(drums[:n], bass[:n], atol=1e-5)
