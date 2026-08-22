"""Characterization: timeline/transport still tick a playhead timer;

MainWindow play/pause/stop now go through AudioEngine as well.
"""

import inspect
from unittest.mock import patch

from PyQt6.QtCore import QTimer

from audio_engine import AudioEngine
from main_window import MainWindow
from timeline import TimelineWidget
from transport_controls import TransportControls


def test_timeline_start_playback_starts_playhead_timer(qapp):
    """start_playback() sets is_playing and starts the 50ms playback_timer."""
    widget = TimelineWidget()
    assert isinstance(widget.playback_timer, QTimer)
    assert widget.playback_timer.interval() == 50
    assert widget.is_playing is False
    assert not widget.playback_timer.isActive()

    widget.start_playback()
    try:
        assert widget.is_playing is True
        assert widget.playback_timer.isActive()
    finally:
        widget.stop_playback()


def test_timeline_start_playback_source_is_timer_not_audio():
    """Timeline start_playback still only starts playback_timer (no engine I/O)."""
    source = inspect.getsource(TimelineWidget.start_playback)
    assert "is_playing" in source
    assert "playback_timer.start" in source
    assert "AudioEngine" not in source
    assert "audio_engine" not in source
    assert "sounddevice" not in source
    assert "OutputStream" not in source


def test_timeline_update_playhead_increments_by_50ms():
    """_update_playhead increments playhead_position by 0.05 (50ms tick)."""
    source = inspect.getsource(TimelineWidget._update_playhead)
    assert "playhead_position" in source
    assert "0.05" in source
    assert "AudioEngine" not in source
    assert "sounddevice" not in source


def test_timeline_update_playhead_runtime_increment(qapp):
    """Calling _update_playhead while playing advances playhead by 0.05s."""
    widget = TimelineWidget()
    widget.start_playback()
    try:
        before = widget.playhead_position
        widget._update_playhead()
        assert widget.playhead_position == before + 0.05
    finally:
        widget.stop_playback()


def test_transport_on_play_starts_update_timer_not_audio(qapp):
    """TransportControls._on_play starts its own 50ms update_timer."""
    source = inspect.getsource(TransportControls._on_play)
    assert "update_timer.start" in source
    assert "AudioEngine" not in source
    assert "sounddevice" not in source

    display_src = inspect.getsource(TransportControls._update_display)
    assert "current_time" in display_src
    assert "0.05" in display_src

    transport = TransportControls()
    assert isinstance(transport.update_timer, QTimer)
    assert transport.update_timer.interval() == 50
    assert not transport.update_timer.isActive()

    transport._on_play(True)
    try:
        assert transport.is_playing is True
        assert transport.update_timer.isActive()
        before = transport.current_time
        transport._update_display()
        assert transport.current_time == before + 0.05
    finally:
        transport._on_stop()


def test_main_window_on_play_source_calls_engine_play():
    """MainWindow._on_play calls audio_engine.play with the timeline playhead."""
    source = inspect.getsource(MainWindow._on_play)
    assert "self.audio_engine.play(start_position=self.timeline.playhead_position)" in source
    assert "timeline.start_playback" in source


def test_main_window_transport_routes_to_engine(qapp):
    """Play/pause/stop on MainWindow call the engine and keep the playhead timer."""
    win = MainWindow()
    try:
        assert isinstance(win.audio_engine, AudioEngine)
        start_pos = win.timeline.playhead_position

        with patch.object(win.audio_engine, "play") as play, \
             patch.object(win.audio_engine, "pause") as pause, \
             patch.object(win.audio_engine, "stop") as stop:
            win._on_play()
            play.assert_called_once_with(start_position=start_pos)
            assert win.status_label.text() == "Playing..."
            assert win.timeline.is_playing is True
            assert win.timeline.playback_timer.isActive()

            win._on_pause()
            pause.assert_called_once()
            assert win.status_label.text() == "Paused"

            win._on_stop()
            stop.assert_called_once()
            assert win.status_label.text() == "Stopped"
            assert win.timeline.is_playing is False
    finally:
        win.timeline.stop_playback()
        win.close()
