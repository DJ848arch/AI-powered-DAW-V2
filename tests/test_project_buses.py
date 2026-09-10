"""ProjectManager persist/restore of named buses in .daw (schema 1.0 additive)."""

import json

import numpy as np

from audio_engine import AudioEngine
from project import ProjectManager

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


def _bare_project(**extra):
    data = {
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
    data.update(extra)
    return data


def test_persist_named_bus_in_daw_json(tmp_path, qapp):
    """A) Persist: add_bus('drum'); 0→drum; JSON has version 1.0, buses, dest."""
    pm = _pm(tmp_path)
    engine = AudioEngine(sample_rate=SR)
    engine.add_bus("drum")
    engine.set_track_output(0, "drum")
    project = pm.new_project("Buses")
    path = str(tmp_path / "buses.daw")

    assert pm.save_project(path, project, engine=engine) is True

    with open(path, "r") as f:
        data = json.load(f)
    assert data["version"] == "1.0"
    assert "buses" in data
    assert "drum" in data["buses"]
    dest = _dest_for_track(data.get("track_outputs"), 0)
    assert dest == "drum"


def test_missing_buses_key_is_no_buses(tmp_path, qapp):
    """B) Missing buses key: 1.0 .daw without 'buses' loads; no buses; dests master."""
    pm = _pm(tmp_path)
    path = str(tmp_path / "nobuses.daw")
    with open(path, "w") as f:
        json.dump(_bare_project(), f)

    engine = AudioEngine(sample_rate=SR)
    loaded = pm.load_project(path, engine=engine)
    assert "buses" not in loaded
    assert engine.list_buses() == []
    assert engine.get_track_output(0) == "master"


def test_restore_order_add_bus_before_dest(tmp_path, qapp):
    """C) Restore order: fresh engine load; drum listed; get_track_output(0)=='drum'."""
    pm = _pm(tmp_path)
    engine_a = AudioEngine(sample_rate=SR)
    engine_a.add_bus("drum")
    engine_a.set_track_output(0, "drum")
    project = pm.new_project("Restore")
    path = str(tmp_path / "restore.daw")
    assert pm.save_project(path, project, engine=engine_a) is True

    engine_b = AudioEngine(sample_rate=SR)
    pm.load_project(path, engine=engine_b)
    assert "drum" in engine_b.list_buses()
    assert engine_b.get_track_output(0) == "drum"


def test_roundtrip_mix_tone_via_bus(tmp_path, qapp):
    """D) Round-trip mix: 0→drum on A, load on B; mix() audible (~tanh(0.4))."""
    pm = _pm(tmp_path)
    n = SR
    tone = _tone(n, 0.4)

    engine_a = AudioEngine(sample_rate=SR)
    engine_a.load_audio(0, tone)
    engine_a.add_bus("drum")
    engine_a.set_track_output(0, "drum")
    project = pm.new_project("Mix")
    path = str(tmp_path / "mix.daw")
    assert pm.save_project(path, project, engine=engine_a) is True

    engine_b = AudioEngine(sample_rate=SR)
    engine_b.load_audio(0, tone)
    pm.load_project(path, engine=engine_b)
    mixed = engine_b.mix()
    expected = np.float32(np.tanh(0.4))
    assert np.allclose(mixed, expected, atol=1e-5)
    assert np.max(np.abs(mixed)) > 1e-4


def test_main_window_file_save_load_survives_clear(tmp_path, qapp):
    """E) File save/load via MainWindow: buses+dest survive clear() then reapply."""
    from main_window import MainWindow

    path = str(tmp_path / "mw_buses.daw")
    win_a = MainWindow()
    try:
        win_a.audio_engine.add_bus("drum")
        win_a.audio_engine.set_track_output(0, "drum")
        win_a._do_save(path)
    finally:
        win_a.close()

    with open(path, "r") as f:
        data = json.load(f)
    assert data["version"] == "1.0"
    assert "drum" in data.get("buses", [])
    dest = _dest_for_track(data.get("track_outputs"), 0)
    assert dest == "drum"

    win_b = MainWindow()
    try:
        assert win_b.audio_engine.get_track_output(0) == "master"
        assert "drum" not in win_b.audio_engine.list_buses()
        loaded = win_b.project_manager.load_project(path, engine=win_b.audio_engine)
        win_b._load_project_data(loaded)
        assert win_b.audio_engine.get_track_output(0) == "drum"
        assert "drum" in win_b.audio_engine.list_buses()
    finally:
        win_b.close()
