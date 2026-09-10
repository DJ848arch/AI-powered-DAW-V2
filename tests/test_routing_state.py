"""Expanded M1 routing-state characterization (ClickUp 86bbpaktj).

Cross-surface: persist keys, missing-key defaults, cycles, graph validation,
bus restore-before-dest, picker→engine, first-slice sends, source-fader/send
scaling. Send levels / inserts skip until Engine lands them. Unused-bus-only
Unused-bus File>Open residual is covered (UI re-applies buses after clear).
"""

import copy
import json

import numpy as np
import pytest

from audio_engine import AudioEngine
from project import ProjectManager

SCHEMA = ProjectManager.SCHEMA_VERSION


SR = 8000


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


def _combo_labels(widget):
    combo = widget.dest_combo
    return [combo.itemText(i) for i in range(combo.count())]


# ---------------------------------------------------------------------------
# Persist keys / missing-key defaults
# ---------------------------------------------------------------------------


def test_persist_keys_buses_dest_and_sends(tmp_path, qapp):
    """Save with bus, dest, and send: .daw 1.1 has buses + dest + sends.

    Engine get_state() still omits buses/sends (M1 lock; Core is the adapter).
    """
    pm = _pm(tmp_path)
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.add_bus("drum")
    engine.set_track_output(0, "drum")
    engine.add_send(0, "drum")
    path = str(tmp_path / "keys.daw")
    assert pm.save_project(path, pm.new_project("Keys"), engine=engine) is True

    with open(path, "r") as f:
        data = json.load(f)
    assert data["version"] == SCHEMA
    assert "drum" in data.get("buses", [])
    assert _dest_for_track(data.get("track_outputs"), 0) == "drum"
    assert data.get("track_sends", {}).get("0") == ["drum"]
    assert data.get("track_send_levels", {}).get("0", {}).get("drum") == 1.0
    assert "sends" not in data

    state = engine.get_state()
    assert "buses" not in state
    assert "sends" not in state
    assert "track_sends" not in state
    assert engine.get_sends(0) == ["drum"]


def test_missing_keys_default_master_no_buses_no_sends(tmp_path, qapp):
    """1.0 .daw without buses/track_outputs/sends → master, no buses, no sends."""
    pm = _pm(tmp_path)
    path = str(tmp_path / "missing.daw")
    with open(path, "w") as f:
        json.dump(_bare_project(), f)

    engine = AudioEngine(sample_rate=SR)
    loaded = pm.load_project(path, engine=engine)
    assert loaded.get("buses") == []
    assert not loaded.get("track_outputs")
    assert not loaded.get("track_sends")
    assert "sends" not in loaded
    assert engine.list_buses() == []
    assert engine.get_track_output(0) == "master"
    assert engine.get_sends(0) == []


def test_empty_buses_list_is_no_buses(tmp_path, qapp):
    pm = _pm(tmp_path)
    path = str(tmp_path / "empty_buses.daw")
    with open(path, "w") as f:
        json.dump(_bare_project(buses=[], track_outputs={}), f)

    engine = AudioEngine(sample_rate=SR)
    pm.load_project(path, engine=engine)
    assert engine.list_buses() == []
    assert engine.get_track_output(0) == "master"


# ---------------------------------------------------------------------------
# Cycles / graph validation
# ---------------------------------------------------------------------------


def test_validate_routing_rejects_stored_cycle_without_mutate(qapp):
    """validate_routing is an alias of validate_graph; stuffed 0→1→0 raises."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.load_audio(1, _tone(64, 0.3))
    engine.track_outputs[0] = 1
    engine.track_outputs[1] = 0
    before = copy.deepcopy(dict(engine.track_outputs))
    with pytest.raises(ValueError, match="cycle"):
        engine.validate_routing()
    assert engine.track_outputs == before
    assert engine.validate_routing is not None


def test_send_does_not_trip_main_output_cycle(qapp):
    """Sends are extra: 1→0 on main, send 0→1 is allowed (not a setter cycle)."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.load_audio(1, _tone(64, 0.3))
    engine.set_track_output(1, 0)
    engine.add_send(0, 1)
    assert engine.get_track_output(0) == "master"
    assert engine.get_sends(0) == [1]
    assert engine.validate_graph() is None


# ---------------------------------------------------------------------------
# Bus restore-before-dest
# ---------------------------------------------------------------------------


def test_restore_add_bus_before_named_dest(tmp_path, qapp):
    """Fresh engine: add_bus must run before 0→drum or dest would be unknown."""
    pm = _pm(tmp_path)
    engine_a = AudioEngine(sample_rate=SR)
    engine_a.add_bus("drum")
    engine_a.set_track_output(0, "drum")
    path = str(tmp_path / "order.daw")
    assert pm.save_project(path, pm.new_project("Order"), engine=engine_a) is True

    engine_b = AudioEngine(sample_rate=SR)
    pm.load_project(path, engine=engine_b)
    assert "drum" in engine_b.list_buses()
    assert engine_b.get_track_output(0) == "drum"

    # Wrong order on a third engine: dest first is skipped as unknown bus.
    engine_c = AudioEngine(sample_rate=SR)
    with pytest.raises(ValueError):
        engine_c.set_track_output(0, "drum")
    engine_c.add_bus("drum")
    assert engine_c.get_track_output(0) == "master"


# ---------------------------------------------------------------------------
# Sends: extra copy + source-fader scaling
# ---------------------------------------------------------------------------


def test_source_fader_scales_send_copy(qapp):
    """Send is a post-fader copy of the source's own clips (source vol 0.5)."""
    engine = AudioEngine(sample_rate=SR)
    amp = 0.4
    engine.load_audio(0, _tone(SR, amp))
    engine.add_bus("fx")
    engine.add_send(0, "fx")
    engine.set_track_volume(0, 0.5)
    mixed = engine.mix()
    expected = np.float32(np.tanh(amp * 0.5 + amp * 0.5))
    assert np.allclose(mixed, expected, atol=1e-5)
    assert engine.get_track_output(0) == "master"


def test_send_to_track_is_extra_before_dest_fader(qapp):
    """Send 0→1 adds own clips into dest before dest fader; 0 still to master."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, 0.4))
    engine.load_audio(1, _tone(SR, 0.0))
    engine.add_send(0, 1)
    engine.set_track_volume(1, 0.5)
    mixed = engine.mix()
    # Main 0 at 0.4 to master + send copy 0.4 through dest fader 0.5.
    expected = np.float32(np.tanh(0.4 + 0.4 * 0.5))
    assert np.allclose(mixed, expected, atol=1e-5)
    assert engine.get_track_output(0) == "master"


# ---------------------------------------------------------------------------
# Picker → engine, including bus dest after File>Open
# ---------------------------------------------------------------------------


def test_picker_bus_dest_roundtrip_file_open(tmp_path, qapp):
    """Out combo lists drum, writes set_track_output, File>Open syncs combo."""
    from main_window import MainWindow

    path = str(tmp_path / "picker_bus.daw")
    win_a = MainWindow()
    try:
        t0 = win_a.track_panel.add_track("Kick")
        win_a.audio_engine.add_bus("drum")
        win_a.track_panel.sync_outputs_from_engine(win_a.audio_engine)
        w0 = win_a.track_panel.tracks[t0]
        assert "drum" in _combo_labels(w0)
        idx = w0.dest_combo.findData("drum")
        assert idx >= 0
        w0.dest_combo.setCurrentIndex(idx)
        assert win_a.audio_engine.get_track_output(t0) == "drum"
        win_a._do_save(path)
    finally:
        win_a.close()

    win_b = MainWindow()
    try:
        data = win_b.project_manager.load_project(path, engine=win_b.audio_engine)
        win_b._load_project_data(data)
        ids = sorted(win_b.track_panel.tracks)
        assert ids
        src = ids[0]
        assert win_b.audio_engine.get_track_output(src) == "drum"
        assert "drum" in win_b.audio_engine.list_buses()
        combo = win_b.track_panel.tracks[src].dest_combo
        assert combo.currentData() == "drum"
        assert "drum" in _combo_labels(win_b.track_panel.tracks[src])
    finally:
        win_b.close()


# ---------------------------------------------------------------------------
# Unused-bus-only File>Open residual (known)
# ---------------------------------------------------------------------------


def test_unused_bus_survives_file_open_after_clear(tmp_path, qapp):
    """add_bus with no dest: File>Open should still list the bus (residual)."""
    from main_window import MainWindow

    path = str(tmp_path / "unused_bus.daw")
    win_a = MainWindow()
    try:
        win_a.audio_engine.add_bus("drum")
        assert "drum" in win_a.audio_engine.list_buses()
        assert win_a.audio_engine.get_track_output(0) == "master"
        win_a._do_save(path)
    finally:
        win_a.close()

    with open(path, "r") as f:
        data = json.load(f)
    assert "drum" in data.get("buses", [])

    win_b = MainWindow()
    try:
        loaded = win_b.project_manager.load_project(path, engine=win_b.audio_engine)
        win_b._load_project_data(loaded)
        assert "drum" in win_b.audio_engine.list_buses()
    finally:
        win_b.close()


def test_unused_bus_survives_engine_load_without_ui_clear(tmp_path, qapp):
    """ProjectManager.load_project restores unused buses (no UI clear)."""
    pm = _pm(tmp_path)
    engine_a = AudioEngine(sample_rate=SR)
    engine_a.add_bus("drum")
    path = str(tmp_path / "unused_engine.daw")
    assert pm.save_project(path, pm.new_project("Unused"), engine=engine_a) is True

    engine_b = AudioEngine(sample_rate=SR)
    pm.load_project(path, engine=engine_b)
    assert "drum" in engine_b.list_buses()
    assert engine_b.get_track_output(0) == "master"


# ---------------------------------------------------------------------------
# Send levels / inserts (landed)
# ---------------------------------------------------------------------------


def test_send_level_scales_extra_copy(qapp):
    engine = AudioEngine(sample_rate=SR)
    amp = 0.4
    engine.load_audio(0, _tone(SR, amp))
    engine.add_bus("fx")
    engine.add_send(0, "fx")
    engine.set_send_level(0, "fx", 0.5)
    mixed = engine.mix()
    expected = np.float32(np.tanh(amp + amp * 0.5))
    assert np.allclose(mixed, expected, atol=1e-5)
    assert engine.get_track_output(0) == "master"


def test_inserts_scale_main_and_send_not_other_tracks(qapp):
    """On-channel 0.5 insert: both main and send scaled; other tracks dry."""
    from effects_rack import clear_test_inserts, set_test_insert

    clear_test_inserts()
    try:
        engine = AudioEngine(sample_rate=SR)
        amp = 0.4
        engine.load_audio(0, _tone(SR, amp))
        engine.load_audio(1, _tone(SR, 0.3))
        engine.add_bus("fx")
        engine.add_send(0, "fx", level=1.0)
        set_test_insert(0, gain=0.5)
        mixed = engine.mix()
        # Track 0 insert 0.5 on main+send; track 1 unchanged.
        expected = np.float32(np.tanh(amp * 0.5 + amp * 0.5 + 0.3))
        assert np.allclose(mixed, expected, atol=1e-5)
        leaked = np.float32(np.tanh(amp * 0.5 + amp * 0.5 + 0.3 * 0.5))
        assert not np.allclose(mixed, leaked, atol=1e-5)
    finally:
        clear_test_inserts()
