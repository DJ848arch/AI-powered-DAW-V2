"""M3 mixer foundation tests."""

from audio_engine import AudioEngine
from mixer_widget import MixerWidget


def test_mixer_builds_track_bus_and_master_strips(qapp):
    engine = AudioEngine()
    engine.initialize()
    engine.set_track_volume(0, 0.75)
    engine.set_track_pan(0, -0.25)
    engine.add_bus("drum")

    mixer = MixerWidget(engine)
    assert ("track", 0) in mixer.strips
    assert ("bus", "drum") in mixer.strips
    assert ("master", "master") in mixer.strips
    assert mixer.strips[("track", 0)].fader.value() == 75
    assert mixer.strips[("track", 0)].pan.value() == -25


def test_track_strip_writes_to_engine(qapp):
    engine = AudioEngine()
    engine.initialize()
    engine.set_track_volume(0, 1.0)
    mixer = MixerWidget(engine)
    strip = mixer.strips[("track", 0)]

    strip.fader.setValue(42)
    strip.pan.setValue(30)
    strip.mute.setChecked(True)
    strip.solo.setChecked(True)

    assert engine.track_volumes[0] == 0.42
    assert engine.track_pans[0] == 0.30
    assert engine.track_mutes[0] is True
    assert engine.track_solos[0] is True


def test_bus_strip_writes_to_engine(qapp):
    engine = AudioEngine()
    engine.initialize()
    engine.add_bus("fx")
    mixer = MixerWidget(engine)
    strip = mixer.strips[("bus", "fx")]

    strip.fader.setValue(55)
    strip.pan.setValue(-40)

    assert engine.get_bus_volume("fx") == 0.55
    assert engine.get_bus_pan("fx") == -0.40


def test_mixer_uses_engine_meter_data(qapp):
    engine = AudioEngine()
    engine.initialize()
    engine.set_track_volume(0, 1.0)
    mixer = MixerWidget(engine)

    engine._meters = {
        "tracks": {0: {"peak": 0.5, "rms": 0.25}},
        "buses": {},
        "master": {"peak": 0.75, "rms": 0.5},
    }
    mixer.update_meters()

    assert mixer.strips[("track", 0)].meter.value() == 500
    assert mixer.strips[("master", "master")].meter.value() == 750


def test_mixer_rebuild_tracks_live_bus_changes(qapp):
    engine = AudioEngine()
    engine.initialize()
    engine.set_track_volume(0, 1.0)
    mixer = MixerWidget(engine)

    engine.add_bus("vox")
    mixer.sync_from_engine()
    assert ("bus", "vox") in mixer.strips

    engine.remove_bus("vox")
    mixer.sync_from_engine()
    assert ("bus", "vox") not in mixer.strips


def test_track_strip_edits_inserts_and_sends(qapp):
    engine = AudioEngine()
    engine.initialize()
    engine.set_track_volume(0, 1.0)
    engine.set_track_volume(1, 1.0)
    engine.add_bus("fx")
    mixer = MixerWidget(engine)
    strip = mixer.strips[("track", 0)]

    strip.insert_type.setCurrentText("gain")
    strip._add_insert()
    assert engine.get_inserts(0)[0]["type"] == "gain"

    for i in range(strip.send_dest.count()):
        if strip.send_dest.itemData(i) == "fx":
            strip.send_dest.setCurrentIndex(i)
            break
    strip.send_mode.setCurrentText("pre")
    strip._add_send()
    assert "fx" in engine.get_sends(0)
    assert engine.get_send_mode(0, "fx") == "pre"

    strip._set_combo_value("fx", combo=strip.send_select)
    strip.send_level.setValue(35)
    assert engine.get_send_level(0, "fx") == 0.35

    strip.send_mode.setCurrentText("post")
    assert engine.get_send_mode(0, "fx") == "post"

    strip._remove_send()
    assert "fx" not in engine.get_sends(0)
    strip._clear_inserts()
    assert engine.get_inserts(0) == []


def test_main_window_mixer_is_engine_backed_and_syncs_track_panel(qapp):
    from main_window import MainWindow

    win = MainWindow()
    try:
        tid = win.track_panel.add_track("Vox")
        win.timeline.add_track(tid)
        win._sync_mixer()
        strip = win.mixer_widget.strips[("track", tid)]

        strip.fader.setValue(63)
        strip.pan.setValue(-20)
        strip.mute.setChecked(True)

        assert win.audio_engine.track_volumes[tid] == 0.63
        assert win.audio_engine.track_pans[tid] == -0.20
        assert win.audio_engine.track_mutes[tid] is True
        assert win.track_panel.tracks[tid].get_volume() == 0.63
        assert win.track_panel.tracks[tid].get_pan() == -0.20
        assert win.track_panel.tracks[tid].is_muted() is True
        assert win.is_modified is True
    finally:
        win.meter_timer.stop()
        win.close()


def test_main_window_track_panel_changes_sync_to_mixer(qapp):
    from main_window import MainWindow

    win = MainWindow()
    try:
        tid = win.track_panel.add_track("Bass")
        win.timeline.add_track(tid)
        widget = win.track_panel.tracks[tid]
        widget.volume_slider.setValue(47)
        widget.pan_slider.setValue(10)
        widget.solo_btn.setChecked(True)

        strip = win.mixer_widget.strips[("track", tid)]
        assert win.audio_engine.track_volumes[tid] == 0.47
        assert win.audio_engine.track_pans[tid] == 0.20
        assert win.audio_engine.track_solos[tid] is True
        assert strip.fader.value() == 47
        assert strip.pan.value() == 20
        assert strip.solo.isChecked() is True
    finally:
        win.meter_timer.stop()
        win.close()


def test_clear_audio_preserves_mixer_graph(qapp):
    engine = AudioEngine()
    engine.initialize()
    engine.set_track_volume(0, 0.6)
    engine.add_bus("fx")
    engine.set_track_output(0, "fx")
    engine.add_insert(0, {"type": "gain", "enabled": True})
    engine.add_send(0, "fx", level=0.4, mode="pre")

    engine.clear_audio()

    assert engine.track_volumes[0] == 0.6
    assert engine.get_track_output(0) == "fx"
    assert "fx" in engine.list_buses()
    assert engine.get_inserts(0)[0]["type"] == "gain"
    assert engine.get_sends(0) == ["fx"]
    assert engine.get_send_level(0, "fx") == 0.4
    assert engine.get_send_mode(0, "fx") == "pre"
