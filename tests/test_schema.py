"""M2 schema 1.1: unified graph round-trip + M1 .daw migration.

Does not invent audio-backed graph QA (later M2 slice). Mix checks here
are only the trivial dest/send restore already covered in M1.
"""

import json

import numpy as np
import pytest

from audio_engine import AudioEngine
from project import ProjectManager


SR = 8000
SCHEMA_1_1 = ProjectManager.SCHEMA_VERSION


def _tone(n, value=0.5):
    return np.full((n, 2), value, dtype=np.float32)


def _pm(tmp_path):
    return ProjectManager(projects_dir=str(tmp_path / "projects"))


def _dest_for_track(mapping, track_id):
    if mapping is None:
        return None
    if track_id in mapping:
        return mapping[track_id]
    return mapping.get(str(track_id))


def _m1_bare(**extra):
    """On-disk M1 1.0 shape (missing graph keys, as shipped)."""
    data = {
        "version": "1.0",
        "name": "M1 Bare",
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


def test_new_project_is_schema_1_1():
    pm = ProjectManager(projects_dir="/tmp/aria-schema-unused")
    project = pm.new_project("Schema")
    assert project["version"] == SCHEMA_1_1
    assert project["track_outputs"] == {}
    assert project["buses"] == []
    assert project["track_sends"] == {}
    assert project["track_send_levels"] == {}
    assert project["inserts"] == {}
    assert "tracks" in project
    assert "timeline" in project
    assert "transport" in project


def test_unified_schema_roundtrip_tracks_buses_routing_sends_inserts(tmp_path, qapp):
    """Save/load the 1.1 graph keys that exist today (no new DSP)."""
    pm = _pm(tmp_path)
    engine_a = AudioEngine(sample_rate=SR)
    engine_a.load_audio(0, _tone(64, 0.2))
    engine_a.load_audio(1, _tone(64, 0.3))
    engine_a.add_bus("drum")
    engine_a.add_bus("fx")
    engine_a.set_track_output(0, "drum")
    engine_a.set_track_output(1, 0)
    engine_a.add_send(0, "fx", level=0.5)

    project = pm.new_project("Roundtrip")
    project["tracks"]["0"] = pm.new_track(0, name="Kick", instrument="drums")
    project["inserts"] = {"0": [{"type": "identity", "enabled": True}]}
    path = str(tmp_path / "unified.daw")
    assert pm.save_project(path, project, engine=engine_a) is True

    with open(path, "r") as f:
        on_disk = json.load(f)
    assert on_disk["version"] == SCHEMA_1_1
    assert "drum" in on_disk["buses"]
    assert "fx" in on_disk["buses"]
    assert _dest_for_track(on_disk["track_outputs"], 0) == "drum"
    assert int(_dest_for_track(on_disk["track_outputs"], 1)) == 0
    assert on_disk["track_sends"]["0"] == ["fx"]
    assert on_disk["track_send_levels"]["0"]["fx"] == 0.5
    assert on_disk["inserts"]["0"][0]["type"] == "identity"
    assert on_disk["tracks"]["0"]["name"] == "Kick"

    engine_b = AudioEngine(sample_rate=SR)
    engine_b.load_audio(0, _tone(64, 0.2))
    engine_b.load_audio(1, _tone(64, 0.3))
    loaded = pm.load_project(path, engine=engine_b)
    assert loaded["version"] == SCHEMA_1_1
    assert engine_b.list_buses() == ["drum", "fx"]
    assert engine_b.get_track_output(0) == "drum"
    assert engine_b.get_track_output(1) == 0
    assert engine_b.get_sends(0) == ["fx"]
    assert engine_b.get_send_level(0, "fx") == 0.5
    assert loaded["inserts"]["0"][0]["type"] == "identity"
    assert loaded["tracks"]["0"]["instrument"] == "drums"


def test_migrate_m1_daw_missing_keys_default_safely(tmp_path, qapp):
    """Older M1-shaped .daw still opens: master, no buses, no sends."""
    pm = _pm(tmp_path)
    path = tmp_path / "m1_missing.daw"
    path.write_text(json.dumps(_m1_bare()))

    engine = AudioEngine(sample_rate=SR)
    loaded = pm.load_project(str(path), engine=engine)
    assert loaded["version"] == SCHEMA_1_1
    assert loaded.get("buses") == []
    assert loaded.get("track_outputs") == {}
    assert loaded.get("track_sends") == {}
    assert loaded.get("track_send_levels") == {}
    assert loaded.get("inserts") == {}
    assert engine.list_buses() == []
    assert engine.get_track_output(0) == "master"
    assert engine.get_sends(0) == []


def test_migrate_m1_daw_with_buses_and_track_outputs(tmp_path, qapp):
    """M1 1.0 file that already has buses + dests migrates without dropping them."""
    pm = _pm(tmp_path)
    path = tmp_path / "m1_routed.daw"
    path.write_text(
        json.dumps(
            _m1_bare(
                buses=["drum"],
                track_outputs={"0": "drum", "1": 2},
            )
        )
    )

    engine = AudioEngine(sample_rate=SR)
    loaded = pm.load_project(str(path), engine=engine)
    assert loaded["version"] == SCHEMA_1_1
    assert "drum" in loaded["buses"]
    assert _dest_for_track(loaded["track_outputs"], 0) == "drum"
    assert int(_dest_for_track(loaded["track_outputs"], 1)) == 2
    assert loaded["track_sends"] == {}
    assert engine.get_track_output(0) == "drum"
    assert engine.get_track_output(1) == 2
    assert "drum" in engine.list_buses()
    assert engine.get_sends(0) == []


def test_resave_migrated_m1_writes_1_1(tmp_path, qapp):
    pm = _pm(tmp_path)
    src = tmp_path / "old.daw"
    src.write_text(json.dumps(_m1_bare(name="Old", buses=["fx"], track_outputs={"0": "fx"})))
    loaded = pm.load_project(str(src))
    out = str(tmp_path / "rewritten.daw")
    assert pm.save_project(out, loaded) is True

    with open(out, "r") as f:
        data = json.load(f)
    assert data["version"] == SCHEMA_1_1
    assert data["name"] == "Old"
    assert "fx" in data["buses"]
    assert _dest_for_track(data["track_outputs"], 0) == "fx"
    assert data["track_sends"] == {}
    assert data["inserts"] == {}


def test_unknown_keys_survive_migrate_and_save(tmp_path):
    pm = _pm(tmp_path)
    path = tmp_path / "extra.daw"
    path.write_text(json.dumps(_m1_bare(future_flag=True, extra_map={"keep": 1})))
    loaded = pm.load_project(str(path))
    assert loaded["future_flag"] is True
    assert loaded["extra_map"] == {"keep": 1}

    out = str(tmp_path / "extra_out.daw")
    assert pm.save_project(out, loaded) is True
    with open(out, "r") as f:
        data = json.load(f)
    assert data["future_flag"] is True
    assert data["extra_map"] == {"keep": 1}


def test_m1_track_to_master_track_and_cycle_still_hold(tmp_path, qapp):
    """Do not silently break M1 dest defaults, track→track, or cycle reject."""
    pm = _pm(tmp_path)
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.load_audio(1, _tone(64, 0.3))
    assert engine.get_track_output(0) == "master"

    engine.set_track_output(0, 1)
    path = str(tmp_path / "t2t.daw")
    assert pm.save_project(path, pm.new_project("T2T"), engine=engine) is True

    engine_b = AudioEngine(sample_rate=SR)
    pm.load_project(path, engine=engine_b)
    assert engine_b.get_track_output(0) == 1

    with pytest.raises(ValueError, match="cycle|itself"):
        engine_b.set_track_output(1, 0)
    with pytest.raises(ValueError, match="itself"):
        engine_b.set_track_output(0, 0)
