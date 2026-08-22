"""Characterization: AudioEngine load, mix, start/trim, and offline play.

Proves Engine's rewrite actually places clips and can play without PortAudio.
Does not edit product code.
"""

import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np

from audio_engine import AudioEngine


SR = 8000


def _tone(n, value=0.5):
    """Constant stereo block, amplitude small enough that tanh is still distinctive."""
    return np.full((n, 2), value, dtype=np.float32)


def _ramp(n, lo=0.1, hi=0.9):
    """Mono-unique-per-sample ramp duplicated to stereo."""
    mono = np.linspace(lo, hi, n, dtype=np.float32)
    return np.column_stack((mono, mono))


def _write_wav(path: Path, audio: np.ndarray, sr: int = SR):
    data = np.clip(audio, -1.0, 1.0)
    if data.ndim == 1:
        data = np.column_stack((data, data))
    pcm = (data * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def _assert_stereo_float32(mix):
    assert isinstance(mix, np.ndarray)
    assert mix.dtype == np.float32
    assert mix.ndim == 2
    assert mix.shape[1] == 2


def test_load_audio_accepts_ndarray(qapp):
    engine = AudioEngine(sample_rate=SR)
    audio = _tone(SR)  # 1 second
    rec = engine.load_audio(0, audio)
    assert rec is not None
    assert rec["track_id"] == 0
    assert len(rec["audio"]) == SR
    assert 0 in engine.track_buffers
    assert len(engine.clips) == 1


def test_load_audio_accepts_wav_path(qapp, tmp_path):
    wav = tmp_path / "clip.wav"
    _write_wav(wav, _tone(SR, 0.4))
    engine = AudioEngine(sample_rate=SR)
    rec = engine.load_audio(1, str(wav))
    assert rec is not None
    assert rec["track_id"] == 1
    assert rec["path"] == str(wav)
    assert len(rec["audio"]) == SR
    # path-only form
    engine2 = AudioEngine(sample_rate=SR)
    rec2 = engine2.load_audio(str(wav))
    assert rec2 is not None
    assert len(rec2["audio"]) == SR


def test_mix_and_get_mix_are_stereo_float32(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, 0.5))
    mixed = engine.mix()
    _assert_stereo_float32(mixed)
    got = engine.get_mix()
    _assert_stereo_float32(got)
    assert got.shape == mixed.shape
    # tanh limiter: 0.5 in -> tanh(0.5)
    expected = np.float32(np.tanh(0.5))
    assert np.allclose(mixed[0], expected, atol=1e-5)


def test_clip_start_time_is_silent_before_placement(qapp):
    """A clip with start_time > 0 must not appear at sample 0."""
    engine = AudioEngine(sample_rate=SR)
    audio = _tone(SR, 0.6)  # 1s of signal
    engine.load_audio(0, audio, start_time=0.25)
    mixed = engine.mix()
    _assert_stereo_float32(mixed)
    start = int(round(0.25 * SR))
    assert mixed.shape[0] == start + SR
    # silent (or near-zero) before the clip starts
    assert np.max(np.abs(mixed[:start])) < 1e-6
    # signal after start is the limited tone, not zeros
    expected = np.float32(np.tanh(0.6))
    assert np.allclose(mixed[start : start + 16], expected, atol=1e-5)
    # also via clip dict
    mixed2 = engine.mix(
        clips=[{"audio": audio, "start_time": 0.5, "track_id": 0}]
    )
    start2 = int(round(0.5 * SR))
    assert np.max(np.abs(mixed2[:start2])) < 1e-6
    assert np.allclose(mixed2[start2 : start2 + 8], expected, atol=1e-5)


def test_trim_start_changes_mixed_samples(qapp):
    engine = AudioEngine(sample_rate=SR)
    source = _ramp(SR)
    trim = 0.25
    engine.load_audio(0, source, trim_start=trim)
    mixed = engine.mix()
    cut = int(round(trim * SR))
    assert mixed.shape[0] == SR - cut
    expected = np.tanh(source[cut : cut + 32])
    assert np.allclose(mixed[:32], expected, atol=1e-5)
    # without trim, first samples would be source[0], which is different
    assert not np.allclose(mixed[:32], np.tanh(source[:32]), atol=1e-4)


def test_trim_end_changes_mixed_samples(qapp):
    engine = AudioEngine(sample_rate=SR)
    source = _ramp(SR)
    engine.load_audio(0, source, trim_end=0.5)
    mixed = engine.mix()
    end = int(round(0.5 * SR))
    assert mixed.shape[0] == end
    expected = np.tanh(source[:end])
    assert np.allclose(mixed, expected, atol=1e-4)


def test_duration_caps_mixed_length(qapp):
    engine = AudioEngine(sample_rate=SR)
    source = _ramp(SR)
    engine.load_audio(0, source, duration=0.25)
    mixed = engine.mix()
    n = int(round(0.25 * SR))
    assert mixed.shape[0] == n
    assert np.allclose(mixed, np.tanh(source[:n]), atol=1e-4)


def test_trim_and_duration_together(qapp):
    engine = AudioEngine(sample_rate=SR)
    source = _ramp(SR)
    engine.load_audio(0, source, trim_start=0.25, duration=0.25)
    mixed = engine.mix()
    start = int(round(0.25 * SR))
    n = int(round(0.25 * SR))
    assert mixed.shape[0] == n
    assert np.allclose(mixed, np.tanh(source[start : start + n]), atol=1e-4)


def test_play_offline_without_portaudio_and_stop_resets_position(qapp):
    """play() must work with no device; stop() resets position to 0."""
    engine = AudioEngine(sample_rate=SR, buffer_size=256)
    engine.load_audio(0, _tone(SR, 0.3))

    with patch.object(engine, "has_audio_device", return_value=False):
        engine.play(start_position=0.1)
        try:
            assert engine.is_playing is True
            assert engine._offline_mode is True
            assert engine.stream is None
            _assert_stereo_float32(engine.master_mix)
            assert engine.master_mix.shape[0] == SR
            assert engine.start_position == 0.1
            assert engine.current_position >= 0.1
        finally:
            engine.stop()

    assert engine.is_playing is False
    assert engine.current_position == 0.0
    assert engine.get_position() == 0.0
