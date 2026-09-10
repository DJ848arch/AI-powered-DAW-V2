"""TrackPanel destination picker: Master + other tracks + known buses."""

import json

import pytest

from audio_engine import AudioEngine
from main_window import MainWindow
from track_panel import TrackPanel


def _combo_labels(widget):
    combo = widget.dest_combo
    return [combo.itemText(i) for i in range(combo.count())]


def _combo_values(widget):
    combo = widget.dest_combo
    return [combo.itemData(i) for i in range(combo.count())]


def test_picker_lists_master_and_other_tracks_not_self(qapp):
    panel = TrackPanel()
    t0 = panel.add_track("Kick")
    t1 = panel.add_track("Bass")
    w0 = panel.tracks[t0]
    labels = _combo_labels(w0)
    values = _combo_values(w0)
    assert labels[0] == "Master"
    assert "Bass" in labels
    assert "Kick" not in labels
    assert "master" in values
    assert t1 in values
    assert t0 not in values

    w1 = panel.tracks[t1]
    assert "Kick" in _combo_labels(w1)
    assert t0 in _combo_values(w1)
    assert t1 not in _combo_values(w1)


def test_picker_lists_known_buses(qapp):
    win = MainWindow()
    try:
        t0 = win.track_panel.add_track("Kick")
        t1 = win.track_panel.add_track("Bass")
        win.audio_engine.add_bus("drum")
        win.track_panel.sync_outputs_from_engine(win.audio_engine)
        w0 = win.track_panel.tracks[t0]
        labels = _combo_labels(w0)
        values = _combo_values(w0)
        assert "Master" in labels
        assert "Bass" in labels
        assert "Kick" not in labels
        assert "drum" in labels
        assert "drum" in values
        assert t0 not in values
        assert t1 in values
    finally:
        win.close()


def test_picker_sets_and_reflects_bus_dest(qapp):
    win = MainWindow()
    try:
        t0 = win.track_panel.add_track("Kick")
        win.audio_engine.add_bus("drum")
        win.track_panel.sync_outputs_from_engine(win.audio_engine)
        w0 = win.track_panel.tracks[t0]
        idx = w0.dest_combo.findData("drum")
        assert idx >= 0
        w0.dest_combo.setCurrentIndex(idx)
        assert win.audio_engine.get_track_output(t0) == "drum"
        assert win.track_panel.get_track_output(t0) == "drum"

        win.audio_engine.set_track_output(t0, "master")
        win.track_panel.sync_outputs_from_engine(win.audio_engine)
        assert win.track_panel.get_track_output(t0) == "master"
        win.audio_engine.set_track_output(t0, "drum")
        win.track_panel.sync_outputs_from_engine(win.audio_engine)
        assert win.track_panel.get_track_output(t0) == "drum"
        assert win.track_panel.tracks[t0].dest_combo.currentData() == "drum"
    finally:
        win.close()


def test_picker_sets_engine_dest(qapp):
    win = MainWindow()
    try:
        t0 = win.track_panel.add_track("A")
        t1 = win.track_panel.add_track("B")
        w0 = win.track_panel.tracks[t0]
        idx = w0.dest_combo.findData(t1)
        assert idx >= 0
        w0.dest_combo.setCurrentIndex(idx)
        assert win.audio_engine.get_track_output(t0) == t1
        assert win.track_panel.get_track_output(t0) == t1
    finally:
        win.close()


def test_picker_reflects_get_track_output(qapp):
    win = MainWindow()
    try:
        t0 = win.track_panel.add_track("A")
        t1 = win.track_panel.add_track("B")
        win.audio_engine.set_track_output(t0, t1)
        win.track_panel.sync_outputs_from_engine(win.audio_engine)
        assert win.track_panel.get_track_output(t0) == t1
        assert win.track_panel.tracks[t0].dest_combo.currentData() == t1
    finally:
        win.close()


def test_engine_still_rejects_self_and_unknown(qapp):
    engine = AudioEngine()
    with pytest.raises(ValueError):
        engine.set_track_output(0, 0)
    with pytest.raises(ValueError):
        engine.set_track_output(0, "bus-1")
    with pytest.raises(ValueError):
        engine.set_track_output(0, "not_a_track")
    engine.set_track_output(0, "master")
    assert engine.get_track_output(0) == "master"


def test_cycle_reverts_picker(qapp):
    win = MainWindow()
    try:
        t0 = win.track_panel.add_track("A")
        t1 = win.track_panel.add_track("B")
        win.audio_engine.set_track_output(t0, t1)
        win.track_panel.sync_outputs_from_engine(win.audio_engine)
        w1 = win.track_panel.tracks[t1]
        idx = w1.dest_combo.findData(t0)
        assert idx >= 0
        w1.dest_combo.setCurrentIndex(idx)
        assert win.audio_engine.get_track_output(t1) == "master"
        assert win.track_panel.get_track_output(t1) == "master"
        assert win.audio_engine.get_track_output(t0) == t1
    finally:
        win.close()


def test_reopen_shows_saved_dest(tmp_path, qapp):
    path = str(tmp_path / "dest_picker.daw")
    win_a = MainWindow()
    try:
        t0 = win_a.track_panel.add_track("A")
        t1 = win_a.track_panel.add_track("B")
        w0 = win_a.track_panel.tracks[t0]
        w0.dest_combo.setCurrentIndex(w0.dest_combo.findData(t1))
        assert win_a.audio_engine.get_track_output(t0) == t1
        win_a._do_save(path)
        with open(path, "r") as f:
            data = json.load(f)
        dest = data.get("track_outputs", {}).get(str(t0))
        if dest is None:
            dest = data.get("track_outputs", {}).get(t0)
        assert dest is not None
        assert int(dest) == t1
    finally:
        win_a.close()

    win_b = MainWindow()
    try:
        data = win_b.project_manager.load_project(path, engine=win_b.audio_engine)
        win_b._load_project_data(data)
        ids = sorted(win_b.track_panel.tracks)
        assert len(ids) >= 2
        src, dest_id = ids[0], ids[1]
        assert win_b.audio_engine.get_track_output(src) == dest_id
        assert win_b.track_panel.get_track_output(src) == dest_id
        shown = win_b.track_panel.tracks[src].dest_combo.currentText()
        assert shown == "B"
    finally:
        win_b.close()
