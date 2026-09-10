"""ProjectManager persist/restore of AudioEngine track_outputs (M1)."""

import json

import numpy as np

from audio_engine import AudioEngine
from project import ProjectManager

SCHEMA = ProjectManager.SCHEMA_VERSION

SR = 8000


def _tone(n, value=0.5):
    return np.full((n, 2), value, dtype=np.float32)


def _pm(tmp_path):
    return ProjectManager(projects_dir=str(tmp_path / "projects"))


def _dest_for_track(mapping, track_id):
    """JSON object keys are strings; tolerate int keys too."""
    if mapping is None:
        return None
    if track_id in mapping:
        return mapping[track_id]
    return mapping.get(str(track_id))


def test_persist_track_output_in_daw_json(tmp_path, qapp):
    """A) PERSIST: set 0→1, save with engine; JSON has track_outputs, current schema."""
    pm = _pm(tmp_path)
    engine = AudioEngine(sample_rate=SR)
    engine.set_track_output(0, 1)
    project = pm.new_project("Routed")
    path = str(tmp_path / "routed.daw")

    assert pm.save_project(path, project, engine=engine) is True

    with open(path, "r") as f:
        data = json.load(f)
    assert data["version"] == SCHEMA
    assert "track_outputs" in data
    dest = _dest_for_track(data["track_outputs"], 0)
    assert dest is not None
    assert int(dest) == 1


def test_missing_key_is_master(tmp_path, qapp):
    """B) Missing key = master: no 0→1 (or omitted track_outputs) loads as master."""
    pm = _pm(tmp_path)
    project = pm.new_project("No Route")
    path = str(tmp_path / "noroute.daw")
    assert pm.save_project(path, project) is True

    engine = AudioEngine(sample_rate=SR)
    pm.load_project(path, engine=engine)
    assert engine.get_track_output(0) == "master"

    # Explicitly omitted key still loads; dests stay master.
    omitted = str(tmp_path / "omitted.daw")
    bare = {
        "version": "1.0",
        "name": "Bare",
        "timeline": {"tracks": {}, "clips": {}, "zoom_level": 1.0, "bpm": 120},
        "transport": {
            "bpm": 120,
            "beats_per_bar": 4,
            "beat_unit": 4,
            "metronome_active": False,
            "position": 0.0,
        },
    }
    with open(omitted, "w") as f:
        json.dump(bare, f)
    engine2 = AudioEngine(sample_rate=SR)
    loaded = pm.load_project(omitted, engine=engine2)
    assert "track_outputs" not in loaded or not loaded.get("track_outputs")
    assert engine2.get_track_output(0) == "master"


def test_restore_dest_fader(tmp_path, qapp):
    """C) RESTORE dest fader: 0 still follows 1's volume after open."""
    pm = _pm(tmp_path)
    n = SR
    tone = _tone(n, 0.6)

    engine_a = AudioEngine(sample_rate=SR)
    engine_a.load_audio(0, tone)
    engine_a.set_track_output(0, 1)
    project = pm.new_project("Fader")
    path = str(tmp_path / "fader.daw")
    assert pm.save_project(path, project, engine=engine_a) is True

    engine_b = AudioEngine(sample_rate=SR)
    engine_b.load_audio(0, tone)
    pm.load_project(path, engine=engine_b)
    engine_b.set_track_volume(1, 0.0)
    silent = engine_b.mix()
    assert np.max(np.abs(silent)) < 1e-6

    engine_b.set_track_volume(1, 1.0)
    audible = engine_b.mix()
    assert np.max(np.abs(audible)) > 1e-4


def test_roundtrip_get_track_output(tmp_path, qapp):
    """D) Roundtrip get_track_output(0)==1 after save/load."""
    pm = _pm(tmp_path)
    engine_a = AudioEngine(sample_rate=SR)
    engine_a.set_track_output(0, 1)
    project = pm.new_project("Roundtrip")
    path = str(tmp_path / "roundtrip.daw")
    assert pm.save_project(path, project, engine=engine_a) is True

    engine_b = AudioEngine(sample_rate=SR)
    pm.load_project(path, engine=engine_b)
    assert engine_b.get_track_output(0) == 1


def test_main_window_file_save_writes_track_outputs(tmp_path, qapp):
    """File>Save of a MainWindow project with 0→1 writes track_outputs."""
    from main_window import MainWindow

    win = MainWindow()
    try:
        win.audio_engine.set_track_output(0, 1)
        path = str(tmp_path / "mw_routed.daw")
        win._do_save(path)

        with open(path, "r") as f:
            data = json.load(f)
        assert "track_outputs" in data
        dest = _dest_for_track(data["track_outputs"], 0)
        assert dest is not None
        assert int(dest) == 1
    finally:
        win.close()


def test_main_window_file_open_reapplies_dests(tmp_path, qapp):
    """File>Open reapplies 0→1 onto a fresh MainWindow engine after clear."""
    from main_window import MainWindow

    path = str(tmp_path / "mw_roundtrip.daw")
    win_a = MainWindow()
    try:
        win_a.audio_engine.set_track_output(0, 1)
        win_a._do_save(path)
    finally:
        win_a.close()

    win_b = MainWindow()
    try:
        assert win_b.audio_engine.get_track_output(0) == "master"
        data = win_b.project_manager.load_project(path, engine=win_b.audio_engine)
        win_b._load_project_data(data)
        assert win_b.audio_engine.get_track_output(0) == 1
    finally:
        win_b.close()
