"""Characterization: MainWindow constructs AudioEngine and wires transport to it."""

import inspect

import main_window
from audio_engine import AudioEngine
from main_window import MainWindow


def test_main_window_module_imports_audio_engine():
    """main_window.py imports AudioEngine."""
    source = inspect.getsource(main_window)
    assert "from audio_engine import AudioEngine" in source


def test_main_window_init_constructs_and_initializes_audio_engine():
    """MainWindow.__init__ builds AudioEngine() and calls initialize()."""
    source = inspect.getsource(MainWindow.__init__)
    assert "self.audio_engine = AudioEngine()" in source
    assert "self.audio_engine.initialize()" in source
    assert "ProjectManager" in source
    assert "_setup_ui" in source


def test_main_window_setup_ui_connects_engine_signals():
    """_setup_ui still builds the layout widgets and connects engine signals."""
    source = inspect.getsource(MainWindow._setup_ui)
    assert "TransportControls" in source
    assert "TrackPanel" in source
    assert "TimelineWidget" in source
    assert "playback_position_changed.connect(self._on_playback_position)" in source
    assert "playback_finished.connect(self._on_engine_finished)" in source
    assert "error_occurred.connect(self._on_engine_error)" in source


def test_on_play_source_calls_engine_play_and_timeline():
    """_on_play sends playhead position to AudioEngine.play, then starts the timeline."""
    source = inspect.getsource(MainWindow._on_play)
    assert "Playing..." in source
    assert "self.audio_engine.play(start_position=self.timeline.playhead_position)" in source
    assert "timeline.start_playback" in source


def test_on_pause_source_calls_engine_pause_and_timeline():
    """_on_pause calls audio_engine.pause and timeline.pause_playback."""
    source = inspect.getsource(MainWindow._on_pause)
    assert "Paused" in source
    assert "self.audio_engine.pause()" in source
    assert "timeline.pause_playback" in source


def test_on_stop_source_calls_engine_stop_and_timeline():
    """_on_stop calls audio_engine.stop and timeline.stop_playback."""
    source = inspect.getsource(MainWindow._on_stop)
    assert "Stopped" in source
    assert "self.audio_engine.stop()" in source
    assert "timeline.stop_playback" in source


def test_close_event_source_stops_audio_engine():
    """closeEvent stops the engine before accepting the close."""
    source = inspect.getsource(MainWindow.closeEvent)
    assert "self.audio_engine.stop()" in source


def test_main_window_owns_audio_engine_instance(qapp):
    """A constructed MainWindow owns an AudioEngine instance."""
    win = MainWindow()
    try:
        assert isinstance(win.audio_engine, AudioEngine)
        assert hasattr(win, "project_manager")
        assert hasattr(win, "transport")
        assert hasattr(win, "track_panel")
        assert hasattr(win, "timeline")
        assert hasattr(win, "chat_widget")
    finally:
        win.close()
