"""Play must render a timeline MidiClip through midi_synth, then load_audio.

UI is wiring that path. These tests are the acceptance bar.
"""

import numpy as np

from main_window import MainWindow
from midi_clip import MidiClip, MidiNote


def _play_offline(win):
    win.audio_engine.has_audio_device = lambda: False
    win._on_play()


def _window_with_midi_clip(qapp, clip):
    win = MainWindow()
    win.timeline.add_track(clip.track_id)
    # add_clip sets clip.start_time from the position argument
    position = getattr(clip, "start_time", 0.0)
    win.timeline.add_clip(clip.track_id, clip, position)
    return win


def _c4_piano(*, start_beat=0.0, duration_beats=1.0, bpm=120.0, track_id=1):
    clip = MidiClip(
        name="c4-piano",
        track_id=track_id,
        instrument="piano",
        bpm=bpm,
        notes=[
            MidiNote(
                pitch=60,
                start_beat=start_beat,
                duration_beats=duration_beats,
                velocity=100,
            )
        ],
    )
    return clip


def test_play_midiclip_c4_piano_is_nonsilent_mix(qapp):
    """C4, 1 beat, piano on the timeline → non-silent mix after offline play."""
    clip = _c4_piano(start_beat=0.0, duration_beats=1.0)
    win = _window_with_midi_clip(qapp, clip)
    try:
        assert clip.id in win.timeline.clips
        _play_offline(win)
        mixed = win.audio_engine.get_mix()
        assert isinstance(mixed, np.ndarray)
        assert mixed.dtype == np.float32
        assert mixed.ndim == 2 and mixed.shape[1] == 2
        assert mixed.shape[0] > 0
        assert np.max(np.abs(mixed)) > 1e-4
    finally:
        win.audio_engine.stop()
        win.close()


def test_play_midiclip_start_beat_silence_holds_on_mix(qapp):
    """A note at start_beat=1 stays silent until that beat on the play mix."""
    bpm = 120.0
    clip = _c4_piano(start_beat=1.0, duration_beats=1.0, bpm=bpm)
    win = _window_with_midi_clip(qapp, clip)
    try:
        _play_offline(win)
        mixed = win.audio_engine.get_mix()
        assert isinstance(mixed, np.ndarray)
        assert mixed.ndim == 2 and mixed.shape[1] == 2
        sr = win.audio_engine.sample_rate
        silent_n = int(round((60.0 / bpm) * sr))  # one beat
        assert mixed.shape[0] > silent_n
        assert np.max(np.abs(mixed[:silent_n])) < 1e-5
        assert np.max(np.abs(mixed[silent_n:])) > 1e-4
    finally:
        win.audio_engine.stop()
        win.close()
