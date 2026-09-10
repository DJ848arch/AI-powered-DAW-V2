"""MIDI clip persistence and additive project instrument fields."""

import json

from midi_clip import MidiClip, MidiNote
from project import ProjectManager


def _pm(tmp_path):
    return ProjectManager(projects_dir=str(tmp_path / "projects"))


def test_midi_clip_to_dict_from_dict_roundtrip():
    clip = MidiClip(
        name="Piano Line",
        track_id=2,
        instrument="lead",
        bpm=140.0,
    )
    clip.add_note(pitch=60, start_beat=0.0, duration_beats=1.0, velocity=100)
    clip.add_note(pitch=64, start_beat=1.0, duration_beats=0.5, velocity=90)

    data = clip.to_dict()
    restored = MidiClip.from_dict(data)

    assert restored.id == clip.id
    assert restored.name == "Piano Line"
    assert restored.track_id == 2
    assert restored.instrument == "lead"
    assert restored.bpm == 140.0
    assert len(restored.notes) == 2
    assert isinstance(restored.notes[0], MidiNote)
    assert restored.notes[0].pitch == 60
    assert restored.notes[0].start_beat == 0.0
    assert restored.notes[0].duration_beats == 1.0
    assert restored.notes[0].velocity == 100
    assert restored.notes[1].pitch == 64
    assert restored.notes[1].start_beat == 1.0
    assert restored.notes[1].duration_beats == 0.5
    assert restored.notes[1].velocity == 90


def test_to_dict_is_file_safe_plain_dicts():
    clip = MidiClip(instrument="bass", bpm=100.0, track_id=1)
    clip.add_note(36, 0.0, 2.0, 80)
    data = clip.to_dict()

    assert data["type"] == "midi"
    assert data["track_id"] == 1
    assert data["instrument"] == "bass"
    assert data["bpm"] == 100.0
    assert isinstance(data["notes"], list)
    assert all(isinstance(n, dict) for n in data["notes"])
    assert data["notes"][0] == {
        "pitch": 36,
        "start_beat": 0.0,
        "duration_beats": 2.0,
        "velocity": 80,
    }

    dumped = json.dumps(data)
    assert "numpy" not in dumped.lower()
    assert "ndarray" not in dumped.lower()
    # A handful of notes, not audio sample blobs.
    assert len(dumped) < 2000

    def _assert_plain(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                assert isinstance(key, str)
                _assert_plain(value)
        elif isinstance(obj, list):
            for item in obj:
                _assert_plain(item)
        else:
            assert isinstance(obj, (str, int, float, bool, type(None)))

    _assert_plain(data)


def test_from_dict_missing_instrument_and_notes():
    clip = MidiClip.from_dict({"id": "abc", "name": "Bare", "track_id": 3})
    assert clip.instrument == "piano"
    assert clip.notes == []
    assert clip.bpm == 120.0
    assert clip.track_id == 3
    assert clip.name == "Bare"
    assert clip.id == "abc"


def test_from_dict_missing_notes_key_is_empty_list():
    clip = MidiClip.from_dict({"instrument": "drums", "bpm": 90})
    assert clip.notes == []
    assert clip.instrument == "drums"
    assert clip.bpm == 90.0
    assert clip.name == "Untitled MIDI"


def test_new_track_includes_instrument():
    pm = ProjectManager(projects_dir="/tmp/aria-midi-unused")
    track = pm.new_track(1, name="Drums", instrument="drums")
    assert track == {
        "id": 1,
        "name": "Drums",
        "instrument": "drums",
        "clips": [],
        "muted": False,
        "solo": False,
    }
    defaulted = pm.new_track(0)
    assert defaulted["name"] == "New Track"
    assert defaulted["instrument"] == "piano"


def test_new_project_version_still_1_0_and_has_midi_clips():
    pm = ProjectManager(projects_dir="/tmp/aria-midi-unused")
    project = pm.new_project("MIDI Project")
    assert project["version"] == "1.0"
    assert "clips" in project
    assert "midi_clips" in project
    assert project["midi_clips"] == {}
    assert project["clips"] == {}


def test_save_load_preserves_track_instrument_and_midi_clips(tmp_path):
    pm = _pm(tmp_path)
    project = pm.new_project("With MIDI")
    assert project["version"] == "1.0"

    track = pm.new_track(0, name="Keys", instrument="piano")
    project["tracks"][str(track["id"])] = track

    clip = MidiClip(
        name="Intro",
        track_id=0,
        instrument="piano",
        bpm=120.0,
    )
    clip.add_note(pitch=72, start_beat=0.0, duration_beats=4.0, velocity=110)
    project["midi_clips"][clip.id] = clip.to_dict()

    path = str(tmp_path / "with_midi.daw")
    assert pm.save_project(path, project) is True

    loaded = pm.load_project(path)
    assert loaded["version"] == "1.0"

    track_rec = loaded["tracks"]["0"]
    assert track_rec["instrument"] == "piano"
    assert track_rec["name"] == "Keys"

    stored = loaded["midi_clips"][clip.id]
    restored = MidiClip.from_dict(stored)
    assert restored.name == "Intro"
    assert restored.instrument == "piano"
    assert restored.bpm == 120.0
    assert restored.track_id == 0
    assert len(restored.notes) == 1
    assert restored.notes[0].pitch == 72
    assert restored.notes[0].start_beat == 0.0
    assert restored.notes[0].duration_beats == 4.0
    assert restored.notes[0].velocity == 110


def test_load_legacy_1_0_without_instrument_or_midi_clips(tmp_path):
    pm = _pm(tmp_path)
    legacy = {
        "version": "1.0",
        "name": "Old Project",
        "timeline": {"tracks": {}, "clips": {}, "zoom_level": 1.0, "bpm": 120},
        "transport": {
            "bpm": 120,
            "beats_per_bar": 4,
            "beat_unit": 4,
            "metronome_active": False,
            "position": 0.0,
        },
        "tracks": {
            "0": {"id": 0, "name": "Audio", "clips": [], "muted": False, "solo": False}
        },
        "clips": {},
    }
    path = tmp_path / "legacy.daw"
    path.write_text(json.dumps(legacy))

    loaded = pm.load_project(str(path))
    assert loaded["version"] == "1.0"
    assert loaded["name"] == "Old Project"
    assert "instrument" not in loaded["tracks"]["0"]
    assert "midi_clips" not in loaded


def test_ensure_track_instrument_fills_missing_only():
    pm = ProjectManager(projects_dir="/tmp/aria-midi-unused")
    bare = {"id": 2, "name": "Old"}
    filled = pm.ensure_track_instrument(bare)
    assert filled["instrument"] == "piano"
    assert filled is bare

    custom = {"id": 3, "name": "Bass", "instrument": "bass"}
    assert pm.ensure_track_instrument(custom)["instrument"] == "bass"
