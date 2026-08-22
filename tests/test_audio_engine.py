"""Characterization: AudioEngine exists and constructs with today's defaults.

Do not call initialize() or play() — those open sounddevice hardware.
"""

import inspect

from PyQt6.QtCore import QObject

from audio_engine import AudioEngine


def test_audio_engine_class_exists_as_qobject_subclass():
    """AudioEngine is a QObject subclass in audio_engine.py."""
    assert inspect.isclass(AudioEngine)
    assert issubclass(AudioEngine, QObject)
    src = inspect.getsource(AudioEngine)
    assert "class AudioEngine(QObject)" in src


def test_audio_engine_default_constructor_sets_today_attrs(qapp):
    """AudioEngine() sets sample_rate, buffer_size, channels, is_playing, position."""
    engine = AudioEngine()
    assert engine.sample_rate == 44100
    assert engine.buffer_size == 1024
    assert engine.channels == 2
    assert engine.is_playing is False
    assert engine.current_position == 0.0


def test_audio_engine_explicit_constructor_args(qapp):
    """AudioEngine(sample_rate=44100, buffer_size=1024) matches today's defaults."""
    engine = AudioEngine(sample_rate=44100, buffer_size=1024)
    assert engine.sample_rate == 44100
    assert engine.buffer_size == 1024
    assert engine.channels == 2
    assert engine.is_playing is False
    assert engine.current_position == 0.0
