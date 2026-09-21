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
