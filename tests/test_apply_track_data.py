"""AgentManager handoff + apply track_data / pop sketch → MidiClips that play.

UI/Core will wire this. These tests are the acceptance bar.
Do not import agent_manager at module level (openjarvis_client is broken).
"""

import inspect

import numpy as np

from main_window import MainWindow
from midi_clip import MidiClip


def _play_offline(win):
    win.audio_engine.has_audio_device = lambda: False
    win._on_play()


def _midi_clips_on_window(win):
    clips = []
    for clip in getattr(win, "midi_clips", []) or []:
        if isinstance(clip, MidiClip):
            clips.append(clip)
    timeline_clips = getattr(getattr(win, "timeline", None), "clips", {}) or {}
    for clip in timeline_clips.values():
        if isinstance(clip, MidiClip) and clip not in clips:
            clips.append(clip)
    return clips


def _find_apply(win):
    names = (
        "apply_track_data",
        "_apply_track_data",
        "apply_agent_track_data",
        "apply_production",
        "apply_pop_sketch",
        "_apply_pop_sketch",
        "apply_fallback_pop_sketch",
    )
    for name in names:
        fn = getattr(win, name, None)
        if callable(fn):
            return fn
    for name, fn in inspect.getmembers(win, predicate=inspect.ismethod):
        if name.startswith("apply") or name.startswith("_apply"):
            src = inspect.getsource(fn)
            if any(token in src for token in ("track_data", "MidiClip", "pop", "midi_patterns")):
                return fn
    return None


def _sample_track_data():
    payload = {
        "created_tracks": [{"track_name": "Piano", "instrument": "piano"}],
        "midi_patterns": [
            {
                "track": "Piano",
                "instrument": "piano",
                "notes": [
                    {
                        "pitch": 60,
                        "start_beat": 0.0,
                        "duration_beats": 1.0,
                        "velocity": 100,
                    }
                ],
                "start_bar": 0,
                "length_bars": 1,
            }
        ],
    }
    try:
        from agent_manager import TrackData

        return TrackData(
            created_tracks=payload["created_tracks"],
            midi_patterns=payload["midi_patterns"],
        )
    except Exception:
        return payload


def test_main_window_constructs_agent_manager_and_gives_it_to_chat(qapp):
    """MainWindow owns an AgentManager and hands it to ChatWidget."""
    win = MainWindow()
    try:
        manager = getattr(win, "agent_manager", None)
        assert manager is not None
        assert manager.__class__.__name__ == "AgentManager"
        assert win.chat_widget.agent_manager is manager
    finally:
        win.close()


def test_apply_track_data_or_pop_sketch_creates_midiclips_with_instruments_and_notes(qapp):
    """Applying track_data (or the fallback pop sketch) creates MidiClips with notes."""
    win = MainWindow()
    try:
        apply_fn = _find_apply(win)
        assert apply_fn is not None, (
            "MainWindow has no apply_track_data / pop-sketch method yet"
        )
        try:
            apply_fn(_sample_track_data())
        except TypeError:
            apply_fn()

        clips = _midi_clips_on_window(win)
        assert clips, "apply created no MidiClips"
        with_notes = [
            c
            for c in clips
            if getattr(c, "instrument", None) and getattr(c, "notes", None)
        ]
        assert with_notes, "MidiClips missing instrument or notes"
    finally:
        win.audio_engine.stop()
        win.close()


def test_after_apply_offline_play_is_nonsilent(qapp):
    """After apply, offline play produces a non-silent mix."""
    win = MainWindow()
    try:
        apply_fn = _find_apply(win)
        assert apply_fn is not None, (
            "MainWindow has no apply_track_data / pop-sketch method yet"
        )
        try:
            apply_fn(_sample_track_data())
        except TypeError:
            apply_fn()

        _play_offline(win)
        mixed = win.audio_engine.get_mix()
        assert isinstance(mixed, np.ndarray)
        assert mixed.ndim == 2 and mixed.shape[1] == 2
        assert mixed.shape[0] > 0
        assert np.max(np.abs(mixed)) > 1e-4
    finally:
        win.audio_engine.stop()
        win.close()
