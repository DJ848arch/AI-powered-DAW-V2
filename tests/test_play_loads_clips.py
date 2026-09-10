"""Characterization: play must (eventually) load timeline clips into AudioEngine.

Today _on_play does not touch timeline.clips. These tests lock that gap
and assert the new contract if UI lands the load-on-play path first.
"""

import inspect

import numpy as np

from clip import AudioClip
from main_window import MainWindow


def _on_play_source() -> str:
    return inspect.getsource(MainWindow._on_play)


def _play_loads_timeline_clips(source: str) -> bool:
    mentions_clips = "timeline.clips" in source or "self.timeline.clips" in source
    loads = "load_audio" in source or "load_clips" in source
    return mentions_clips and loads


def _make_probe_clip(track_id=1, start_time=0.1, trim_start=0.05, trim_end=0.15, sr=44100):
    """0.2s unique ramp so start/trim placement is visible in the mix."""
    n = int(0.2 * sr)
    mono = np.linspace(0.15, 0.85, n, dtype=np.float32)
    audio = np.column_stack((mono, mono))
    return AudioClip(
        name="probe",
        track_id=track_id,
        start_time=start_time,
        audio_data=audio,
        sample_rate=sr,
        trim_start=trim_start,
        trim_end=trim_end,
    )


def _window_with_clip(qapp, clip=None):
    win = MainWindow()
    clip = clip or _make_probe_clip()
    win.timeline.add_track(clip.track_id)
    win.timeline.add_clip(clip.track_id, clip, clip.start_time)
    return win, clip


def _play_offline(win):
    """Drive _on_play without opening PortAudio."""
    win.audio_engine.has_audio_device = lambda: False
    win._on_play()


def test_on_play_source_timeline_clip_loading_contract():
    """_on_play either still skips timeline.clips, or clear+loads them."""
    source = _on_play_source()
    if _play_loads_timeline_clips(source):
        assert "load_audio" in source or "load_clips" in source
        assert "timeline.clips" in source or "self.timeline.clips" in source
        # second play must not stack: clear / reload
        assert (
            "clear(" in source
            or ".clear(" in source
            or "unload" in source
            or "self.audio_engine.clips" in source
        )
    else:
        assert "load_audio" not in source
        assert "load_clips" not in source
        assert "timeline.clips" not in source


def test_after_play_engine_mixes_timeline_clips_at_start_and_trim(qapp):
    """After play, engine has the timeline clip mixed at start_time / trim.

    If UI has not landed yet, play leaves the engine empty (the gap).
    """
    win, clip = _window_with_clip(qapp)
    try:
        assert clip.id in win.timeline.clips
        _play_offline(win)
        engine = win.audio_engine
        source = _on_play_source()
        if _play_loads_timeline_clips(source):
            assert len(engine.clips) >= 1
            mixed = engine.get_mix()
            assert mixed.ndim == 2 and mixed.shape[1] == 2
            assert mixed.dtype == np.float32
            start = int(round(clip.start_time * engine.sample_rate))
            assert np.max(np.abs(mixed[:start])) < 1e-6
            trim_s = int(round(clip.trim_start * clip.sample_rate))
            expected_first = np.tanh(clip.audio_data[trim_s])
            assert np.allclose(mixed[start], expected_first, atol=1e-3)
        else:
            assert len(engine.clips) == 0
            assert clip.id not in {c.get("id") for c in engine.clips}
    finally:
        win.audio_engine.stop()
        win.close()


def test_second_play_does_not_duplicate_clips(qapp):
    """A second play must clear then reload — not stack another copy."""
    win, clip = _window_with_clip(qapp)
    try:
        _play_offline(win)
        win.audio_engine.stop()
        first_count = len(win.audio_engine.clips)
        _play_offline(win)
        second_count = len(win.audio_engine.clips)
        source = _on_play_source()
        if _play_loads_timeline_clips(source):
            assert first_count == 1
            assert second_count == 1
        else:
            assert first_count == 0
            assert second_count == 0
    finally:
        win.audio_engine.stop()
        win.close()
