"""UI↔engine metering wiring: TrackPanel consumes AudioEngine.get_meters()."""

import math

import numpy as np
import pytest

from audio_engine import AudioEngine
from main_window import MainWindow
from track_panel import TrackPanel, TrackWidget


SR = 8000


def _tone(n, value=0.4):
    return np.full((n, 2), value, dtype=np.float32)


def test_track_panel_meters_reflect_engine_after_mix(qapp):
    """After mix with tone + bus, panel meters match engine get_meters (peak > 0)."""
    engine = AudioEngine(sample_rate=SR)
    engine.initialize()
    panel = TrackPanel()
    panel.set_engine(engine)
    tid = panel.add_track("Kick")
    # Align panel track id with engine channel 0 used by load_audio
    assert tid == 0

    engine.load_audio(0, _tone(SR, 0.4))
    engine.add_bus("drum")
    engine.set_track_output(0, "drum")
    engine.set_bus_volume("drum", 0.5)
    engine.mix()

    eng = engine.get_meters()
    assert eng["master"]["peak"] > 1e-4
    assert eng["tracks"][0]["peak"] > 1e-4
    assert eng["buses"]["drum"]["peak"] > 1e-4

    shown = panel.update_meters_from_engine(engine)
    assert shown["master"]["peak"] == eng["master"]["peak"]
    assert shown["master"]["rms"] == eng["master"]["rms"]
    assert shown["tracks"][0]["peak"] == eng["tracks"][0]["peak"]
    assert shown["tracks"][0]["rms"] == eng["tracks"][0]["rms"]
    assert shown["buses"]["drum"]["peak"] == eng["buses"]["drum"]["peak"]
    assert math.isfinite(shown["master"]["peak"])
    assert math.isfinite(shown["master"]["rms"])

    # Widget-level readouts agree
    assert panel.tracks[0].get_meter()["peak"] == eng["tracks"][0]["peak"]
    assert panel.master_meter.get_levels()["peak"] == eng["master"]["peak"]
    assert "drum" in panel._bus_meters
    assert panel._bus_meters["drum"].get_levels()["peak"] == eng["buses"]["drum"]["peak"]


def test_main_window_refresh_meters_after_mix(qapp):
    """MainWindow._refresh_meters pulls engine meters into TrackPanel."""
    win = MainWindow()
    try:
        # Use the window's engine; load tone + bus like engine contract test
        engine = win.audio_engine
        tid = win.track_panel.add_track("Kick")
        engine.load_audio(tid, _tone(SR, 0.4))
        engine.add_bus("drum")
        engine.set_track_output(tid, "drum")
        engine.set_bus_volume("drum", 0.5)
        engine.mix()

        assert hasattr(win, "meter_timer")
        assert hasattr(win, "_refresh_meters")
        win._refresh_meters()

        eng = engine.get_meters()
        shown = win.track_panel.get_displayed_meters()
        assert shown["master"]["peak"] == eng["master"]["peak"]
        assert shown["master"]["peak"] > 1e-4
        assert shown["tracks"][tid]["peak"] == eng["tracks"][tid]["peak"]
        assert shown["buses"]["drum"]["peak"] == eng["buses"]["drum"]["peak"]
        assert shown["buses"]["drum"]["peak"] > 1e-4
    finally:
        win.meter_timer.stop()
        win.close()


def test_missing_channel_shows_zero_no_crash(qapp):
    """Unknown / missing track or bus → 0.0 display, no exception."""
    engine = AudioEngine(sample_rate=SR)
    engine.initialize()
    panel = TrackPanel()
    panel.set_engine(engine)
    tid = panel.add_track("Empty")

    # No mix yet — meters should be zero / missing
    shown = panel.update_meters_from_engine(engine)
    assert shown["tracks"][tid]["peak"] == 0.0
    assert shown["tracks"][tid]["rms"] == 0.0
    assert shown["master"]["peak"] == 0.0

    # Engine get_meter for unknown returns zeros
    missing = engine.get_meter(9999)
    assert missing == {"peak": 0.0, "rms": 0.0}
    ghost = engine.get_meter("no_such_bus")
    assert ghost == {"peak": 0.0, "rms": 0.0}

    # Panel with no engine still safe
    panel2 = TrackPanel()
    panel2.add_track("A")
    out = panel2.update_meters_from_engine(None)
    assert out["master"]["peak"] == 0.0
    assert out["tracks"][0]["peak"] == 0.0


def test_ui_does_not_invent_levels_matches_engine_after_sync(qapp):
    """Smoke: panel values equal engine after sync; UI is display-only."""
    engine = AudioEngine(sample_rate=SR)
    engine.initialize()
    panel = TrackPanel()
    tid = panel.add_track("Tone")
    engine.load_audio(tid, _tone(SR, 0.25))
    engine.mix()
    eng = engine.get_meters()

    panel.update_meters_from_engine(engine)
    shown = panel.get_displayed_meters()
    assert shown["tracks"][tid] == eng["tracks"][tid]
    assert shown["master"] == eng["master"]

    # After a new mix, UI must follow get_meters (not retain prior UI values).
    engine.clear()
    engine.load_audio(tid, _tone(SR, 0.1))
    engine.mix()
    eng2 = engine.get_meters()
    panel.update_meters_from_engine(engine)
    shown2 = panel.get_displayed_meters()
    assert shown2["tracks"][tid]["peak"] == eng2["tracks"][tid]["peak"]
    assert shown2["master"]["peak"] == eng2["master"]["peak"]
    assert shown2["master"]["peak"] != shown["master"]["peak"]


def test_play_starts_meter_timer_stop_clears(qapp):
    """Play starts non-blocking meter timer; stop clears displayed meters."""
    win = MainWindow()
    try:
        tid = win.track_panel.add_track("Kick")
        win.audio_engine.load_audio(tid, _tone(SR, 0.4))
        # Simulate play path without requiring audio device
        win.audio_engine.mix()
        win._refresh_meters()
        assert win.track_panel.get_displayed_meters()["master"]["peak"] > 1e-4

        win.meter_timer.start()
        assert win.meter_timer.isActive()

        win._on_stop()
        assert not win.meter_timer.isActive()
        cleared = win.track_panel.get_displayed_meters()
        assert cleared["master"]["peak"] == 0.0
        assert cleared["tracks"][tid]["peak"] == 0.0
    finally:
        win.meter_timer.stop()
        win.close()


def test_track_widget_set_meter_finite_only(qapp):
    """TrackWidget.set_meter stores finite display values only."""
    w = TrackWidget(0, "T")
    w.set_meter(0.5, 0.25)
    assert w.get_meter() == {"peak": 0.5, "rms": 0.25}
    w.set_meter(float("nan"), float("inf"))
    assert w.get_meter() == {"peak": 0.0, "rms": 0.0}
