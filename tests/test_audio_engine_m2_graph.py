"""M2 second batch: real insert chain, pre/post sends, bus channels, meters.

Feeds a known constant test signal and asserts gain/path behavior.
Does not replace M1 characterization tests — those stay the default-path lock.
"""

import json
import math

import numpy as np
import pytest

from audio_engine import AudioEngine
from effects_rack import apply_insert_chain, clear_test_inserts
from project import ProjectManager


SR = 8000


def _tone(n, value=0.5):
    return np.full((n, 2), value, dtype=np.float32)


def _assert_stereo_float32(mix):
    assert isinstance(mix, np.ndarray)
    assert mix.dtype == np.float32
    assert mix.ndim == 2
    assert mix.shape[1] == 2


def _pm(tmp_path):
    return ProjectManager(projects_dir=str(tmp_path / "projects"))


@pytest.fixture(autouse=True)
def _isolate_test_inserts():
    clear_test_inserts()
    yield
    clear_test_inserts()


# ---------------------------------------------------------------------------
# Insert chain
# ---------------------------------------------------------------------------


def test_empty_insert_chain_is_dry(qapp):
    amp = 0.4
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, amp))
    assert engine.get_inserts(0) == []
    mixed = engine.mix()
    _assert_stereo_float32(mixed)
    assert np.allclose(mixed, np.float32(np.tanh(amp)), atol=1e-5)
    raw = _tone(16, 0.3)
    assert apply_insert_chain(raw, []) is raw
    assert apply_insert_chain(raw, None) is raw


def test_insert_chain_order_offset_then_gain(qapp):
    """offset then gain is not commutative with gain then offset."""
    amp = 0.4
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, amp))
    engine.set_inserts(
        0,
        [
            {"type": "offset", "amount": 0.1, "enabled": True},
            {"type": "gain", "gain": 0.5, "enabled": True},
        ],
    )
    mixed = engine.mix()
    expected = np.float32(np.tanh((amp + 0.1) * 0.5))
    assert np.allclose(mixed, expected, atol=1e-5)

    engine.set_inserts(
        0,
        [
            {"type": "gain", "gain": 0.5, "enabled": True},
            {"type": "offset", "amount": 0.1, "enabled": True},
        ],
    )
    reversed_mix = engine.mix()
    expected_rev = np.float32(np.tanh(amp * 0.5 + 0.1))
    assert np.allclose(reversed_mix, expected_rev, atol=1e-5)
    assert not np.allclose(mixed, reversed_mix, atol=1e-5)


def test_bypassed_and_unknown_insert_slots_are_identity(qapp):
    amp = 0.4
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, amp))
    engine.set_inserts(
        0,
        [
            {"type": "gain", "gain": 0.25, "enabled": False},
            {"type": "not_a_plugin", "gain": 0.1},
            {"type": "passthru"},
        ],
    )
    mixed = engine.mix()
    assert np.allclose(mixed, np.float32(np.tanh(amp)), atol=1e-5)


def test_insert_chain_scales_main_and_send(qapp):
    amp = 0.4
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, amp))
    engine.add_bus("fx")
    engine.add_send(0, "fx", level=1.0)
    engine.set_inserts(0, [{"type": "gain", "gain": 0.5}])
    mixed = engine.mix()
    expected = np.float32(np.tanh(amp * 0.5 + amp * 0.5))
    assert np.allclose(mixed, expected, atol=1e-5)


def test_inserts_roundtrip_and_remain_audible(tmp_path, qapp):
    pm = _pm(tmp_path)
    amp = 0.4
    engine_a = AudioEngine(sample_rate=SR)
    engine_a.load_audio(0, _tone(64, amp))
    engine_a.set_inserts(0, [{"type": "gain", "gain": 0.5, "enabled": True}])
    path = str(tmp_path / "inserts.daw")
    assert pm.save_project(path, pm.new_project("Inserts"), engine=engine_a) is True

    with open(path, "r") as f:
        on_disk = json.load(f)
    assert on_disk["version"] == ProjectManager.SCHEMA_VERSION
    assert on_disk["inserts"]["0"][0]["type"] == "gain"
    assert on_disk["inserts"]["0"][0]["gain"] == 0.5

    engine_b = AudioEngine(sample_rate=SR)
    engine_b.load_audio(0, _tone(64, amp))
    pm.load_project(path, engine=engine_b)
    assert engine_b.get_inserts(0)[0]["type"] == "gain"
    mixed = engine_b.mix()
    assert np.allclose(mixed, np.float32(np.tanh(amp * 0.5)), atol=1e-5)


# ---------------------------------------------------------------------------
# Sends: level + pre vs post
# ---------------------------------------------------------------------------


def test_send_level_scales_extra_path(qapp):
    amp = 0.4
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, amp))
    engine.add_bus("fx")
    engine.add_send(0, "fx", level=0.5)
    mixed = engine.mix()
    expected = np.float32(np.tanh(amp + amp * 0.5))
    assert np.allclose(mixed, expected, atol=1e-5)


def test_multiple_sends_both_audible(qapp):
    amp = 0.3
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, amp))
    engine.add_bus("fx")
    engine.add_bus("verb")
    engine.add_send(0, "fx", level=1.0)
    engine.add_send(0, "verb", level=0.5)
    assert engine.get_sends(0) == ["fx", "verb"]
    mixed = engine.mix()
    expected = np.float32(np.tanh(amp + amp + amp * 0.5))
    assert np.allclose(mixed, expected, atol=1e-5)


def test_pre_vs_post_fader_send_difference(qapp):
    """Post (default) follows source fader; pre does not. Mute silences both."""
    amp = 0.5
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, amp))
    engine.add_bus("fx")
    engine.add_send(0, "fx", level=1.0, mode="post")
    assert engine.get_send_mode(0, "fx") == "post"

    engine.set_track_volume(0, 0.0)
    post_silent = engine.mix()
    assert np.max(np.abs(post_silent)) < 1e-6

    engine.set_send_mode(0, "fx", "pre")
    assert engine.get_send_mode(0, "fx") == "pre"
    pre_open = engine.mix()
    # Main is silenced by fader 0; pre send still carries insert-dry amp.
    expected_pre = np.float32(np.tanh(amp))
    assert np.allclose(pre_open, expected_pre, atol=1e-5)

    engine.set_track_mute(0, True)
    muted = engine.mix()
    assert np.max(np.abs(muted)) < 1e-6


def test_send_mode_persists_in_1_1(tmp_path, qapp):
    pm = _pm(tmp_path)
    engine_a = AudioEngine(sample_rate=SR)
    engine_a.load_audio(0, _tone(64, 0.4))
    engine_a.add_bus("fx")
    engine_a.add_send(0, "fx", level=0.75, mode="pre")
    path = str(tmp_path / "modes.daw")
    assert pm.save_project(path, pm.new_project("Modes"), engine=engine_a) is True

    with open(path, "r") as f:
        data = json.load(f)
    assert data["track_sends"]["0"] == ["fx"]
    assert data["track_send_levels"]["0"]["fx"] == 0.75
    assert data["track_send_modes"]["0"]["fx"] == "pre"

    engine_b = AudioEngine(sample_rate=SR)
    engine_b.load_audio(0, _tone(64, 0.4))
    pm.load_project(path, engine=engine_b)
    assert engine_b.get_send_mode(0, "fx") == "pre"
    assert engine_b.get_send_level(0, "fx") == 0.75

    engine_b.set_track_volume(0, 0.0)
    mixed = engine_b.mix()
    assert np.allclose(mixed, np.float32(np.tanh(0.4 * 0.75)), atol=1e-5)


def test_invalid_send_dest_still_rejected(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    with pytest.raises(ValueError):
        engine.add_send(0, "ghost")
    with pytest.raises(ValueError):
        engine.add_send(0, "master")
    with pytest.raises(ValueError):
        engine.add_send(0, 0)
    assert engine.get_sends(0) == []


# ---------------------------------------------------------------------------
# Buses as mixer channels
# ---------------------------------------------------------------------------


def test_bus_fader_and_pan_in_graph(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, 0.4))
    engine.add_bus("drum")
    engine.set_track_output(0, "drum")
    unity = engine.mix()
    assert np.allclose(unity, np.float32(np.tanh(0.4)), atol=1e-5)

    engine.set_bus_volume("drum", 0.5)
    half = engine.mix()
    assert np.allclose(half, np.float32(np.tanh(0.4 * 0.5)), atol=1e-5)

    engine.set_bus_pan("drum", 1.0)
    panned = engine.mix()
    # Linear pan +1 → left 0, right 1, then tanh.
    assert np.max(np.abs(panned[:, 0])) < 1e-6
    assert np.allclose(panned[:, 1], np.float32(np.tanh(0.4 * 0.5)), atol=1e-5)


def test_bus_inserts_and_send(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, 0.4))
    engine.add_bus("drum")
    engine.add_bus("fx")
    engine.set_track_output(0, "drum")
    engine.set_inserts("drum", [{"type": "gain", "gain": 0.5}])
    engine.add_send("drum", "fx", level=1.0)
    # drum dest master at 0.2 plus send copy 0.2 through fx (unity) to master.
    mixed = engine.mix()
    expected = np.float32(np.tanh(0.4 * 0.5 + 0.4 * 0.5))
    assert np.allclose(mixed, expected, atol=1e-5)


def test_bus_to_bus_to_master(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, 0.4))
    engine.add_bus("drum")
    engine.add_bus("mix")
    engine.set_track_output(0, "drum")
    engine.set_bus_output("drum", "mix")
    engine.set_bus_volume("mix", 0.5)
    assert engine.validate_graph() is None
    mixed = engine.mix()
    assert np.allclose(mixed, np.float32(np.tanh(0.4 * 0.5)), atol=1e-5)


def test_bus_cycle_and_unknown_dest_rejected(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.add_bus("a")
    engine.add_bus("b")
    engine.set_bus_output("a", "b")
    with pytest.raises(ValueError, match="cycle"):
        engine.set_bus_output("b", "a")
    assert engine.get_bus_output("b") == "master"

    with pytest.raises(ValueError):
        engine.set_bus_output("a", "ghost")
    with pytest.raises(ValueError):
        engine.set_track_output(0, "ghost")
    engine.set_track_output(0, "a")
    with pytest.raises(ValueError, match="cycle"):
        engine.set_bus_output("a", 0)
    assert engine.get_bus_output("a") == "b"
    assert engine.validate_graph() is None


def test_bus_mixer_roundtrip(tmp_path, qapp):
    pm = _pm(tmp_path)
    engine_a = AudioEngine(sample_rate=SR)
    engine_a.load_audio(0, _tone(64, 0.4))
    engine_a.add_bus("drum")
    engine_a.add_bus("mix")
    engine_a.set_track_output(0, "drum")
    engine_a.set_bus_output("drum", "mix")
    engine_a.set_bus_volume("mix", 0.5)
    engine_a.set_bus_pan("mix", 0.0)
    path = str(tmp_path / "busmix.daw")
    assert pm.save_project(path, pm.new_project("BusMix"), engine=engine_a) is True

    with open(path, "r") as f:
        data = json.load(f)
    assert data["version"] == ProjectManager.SCHEMA_VERSION
    assert data["bus_outputs"]["drum"] == "mix"
    assert data["bus_volumes"]["mix"] == 0.5

    engine_b = AudioEngine(sample_rate=SR)
    engine_b.load_audio(0, _tone(64, 0.4))
    pm.load_project(path, engine=engine_b)
    assert engine_b.get_bus_output("drum") == "mix"
    assert engine_b.get_bus_volume("mix") == 0.5
    mixed = engine_b.mix()
    assert np.allclose(mixed, np.float32(np.tanh(0.4 * 0.5)), atol=1e-5)


# ---------------------------------------------------------------------------
# Meters + schema 1.1 still round-trips
# ---------------------------------------------------------------------------


def test_engine_meters_tracks_buses_master(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, 0.4))
    engine.add_bus("drum")
    engine.set_track_output(0, "drum")
    engine.set_bus_volume("drum", 0.5)
    mixed = engine.mix()
    meters = engine.get_meters()
    assert math.isfinite(meters["master"]["peak"])
    assert math.isfinite(meters["master"]["rms"])
    assert meters["master"]["peak"] > 1e-4
    assert 0 in meters["tracks"]
    assert math.isfinite(meters["tracks"][0]["peak"])
    assert "drum" in meters["buses"]
    assert meters["buses"]["drum"]["peak"] > 1e-4
    master = engine.get_meter("master")
    assert master["peak"] == meters["master"]["peak"]
    assert np.allclose(mixed, np.float32(np.tanh(0.4 * 0.5)), atol=1e-5)


def test_schema_1_1_graph_keys_still_roundtrip(tmp_path, qapp):
    pm = _pm(tmp_path)
    engine_a = AudioEngine(sample_rate=SR)
    engine_a.load_audio(0, _tone(64, 0.2))
    engine_a.load_audio(1, _tone(64, 0.3))
    engine_a.add_bus("drum")
    engine_a.add_bus("fx")
    engine_a.set_track_output(0, "drum")
    engine_a.set_track_output(1, 0)
    engine_a.add_send(0, "fx", level=0.5, mode="post")
    engine_a.set_inserts(0, [{"type": "identity", "enabled": True}])
    path = str(tmp_path / "unified.daw")
    assert pm.save_project(path, pm.new_project("Roundtrip"), engine=engine_a) is True

    engine_b = AudioEngine(sample_rate=SR)
    engine_b.load_audio(0, _tone(64, 0.2))
    engine_b.load_audio(1, _tone(64, 0.3))
    loaded = pm.load_project(path, engine=engine_b)
    assert loaded["version"] == ProjectManager.SCHEMA_VERSION
    assert engine_b.list_buses() == ["drum", "fx"]
    assert engine_b.get_track_output(0) == "drum"
    assert engine_b.get_track_output(1) == 0
    assert engine_b.get_sends(0) == ["fx"]
    assert engine_b.get_send_level(0, "fx") == 0.5
    assert engine_b.get_send_mode(0, "fx") == "post"
    assert loaded["inserts"]["0"][0]["type"] == "identity"


# ---------------------------------------------------------------------------
# Fuller known-signal proofs (86bbz6x1c)
# ---------------------------------------------------------------------------


def test_known_signal_meter_peak_rms_exact(qapp):
    """Constant tone: track meter is pre-tanh post-fader; master is tanh'd."""
    amp = 0.4
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, amp))
    mixed = engine.mix()
    expected_master = float(np.tanh(amp))
    assert np.allclose(mixed, np.float32(expected_master), atol=1e-5)

    track = engine.get_meter(0)
    master = engine.get_meter("master")
    assert track["peak"] == pytest.approx(amp, abs=1e-5)
    assert track["rms"] == pytest.approx(amp, abs=1e-5)
    assert master["peak"] == pytest.approx(expected_master, abs=1e-5)
    assert master["rms"] == pytest.approx(expected_master, abs=1e-5)


def test_mute_zeros_track_meter_and_master(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, 0.5))
    engine.set_track_mute(0, True)
    mixed = engine.mix()
    assert np.max(np.abs(mixed)) < 1e-6
    track = engine.get_meter(0)
    assert track["peak"] < 1e-6
    assert track["rms"] < 1e-6
    assert engine.get_meter("master")["peak"] < 1e-6


def test_insert_then_post_send_then_bus_fader_meters(qapp):
    """Insert 0.5 → post send 1.0 to fx → bus fader 0.5; known master + meters."""
    amp = 0.4
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, amp))
    engine.add_bus("fx")
    engine.set_inserts(0, [{"type": "gain", "gain": 0.5}])
    engine.add_send(0, "fx", level=1.0, mode="post")
    engine.set_bus_volume("fx", 0.5)

    mixed = engine.mix()
    # Main: amp*0.5; send post-fader amp*0.5 through bus vol 0.5 → amp*0.25
    expected = float(np.tanh(amp * 0.5 + amp * 0.5 * 0.5))
    assert np.allclose(mixed, np.float32(expected), atol=1e-5)

    meters = engine.get_meters()
    assert meters["tracks"][0]["peak"] == pytest.approx(amp * 0.5, abs=1e-5)
    assert meters["buses"]["fx"]["peak"] == pytest.approx(amp * 0.5 * 0.5, abs=1e-5)
    assert meters["master"]["peak"] == pytest.approx(expected, abs=1e-5)


def test_pre_send_ignores_track_fader_post_follows(qapp):
    """Known signal: vol 0.5 — post send scales, pre send does not."""
    amp = 0.4
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, amp))
    engine.add_bus("fx")
    engine.set_track_volume(0, 0.5)

    engine.add_send(0, "fx", level=1.0, mode="post")
    post_mix = engine.mix()
    # main amp*0.5 + send amp*0.5
    assert np.allclose(post_mix, np.float32(np.tanh(amp * 0.5 + amp * 0.5)), atol=1e-5)

    engine.set_send_mode(0, "fx", "pre")
    pre_mix = engine.mix()
    # main amp*0.5 + pre send amp (no track fader)
    assert np.allclose(pre_mix, np.float32(np.tanh(amp * 0.5 + amp)), atol=1e-5)
    assert not np.allclose(post_mix, pre_mix, atol=1e-5)


def test_send_level_zero_leaves_bus_meter_quiet(qapp):
    """Send level 0: main still meters; bus that only receives the send is quiet."""
    amp = 0.4
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, amp))
    engine.add_bus("fx")
    engine.add_send(0, "fx", level=0.0)
    mixed = engine.mix()
    assert np.allclose(mixed, np.float32(np.tanh(amp)), atol=1e-5)

    meters = engine.get_meters()
    assert meters["tracks"][0]["peak"] == pytest.approx(amp, abs=1e-5)
    # Bus still processed (empty input → zero after fader).
    assert meters["buses"].get("fx", {"peak": 0.0})["peak"] < 1e-6
    assert meters["master"]["peak"] == pytest.approx(float(np.tanh(amp)), abs=1e-5)


def test_bus_path_only_master_meter_matches_tanh(qapp):
    """0→drum with bus vol 0.5: track meter raw fader amp; bus post vol; master tanh."""
    amp = 0.4
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(SR, amp))
    engine.add_bus("drum")
    engine.set_track_output(0, "drum")
    engine.set_bus_volume("drum", 0.5)
    mixed = engine.mix()
    expected = float(np.tanh(amp * 0.5))
    assert np.allclose(mixed, np.float32(expected), atol=1e-5)

    assert engine.get_meter(0)["peak"] == pytest.approx(amp, abs=1e-5)
    assert engine.get_meter("drum")["peak"] == pytest.approx(amp * 0.5, abs=1e-5)
    assert engine.get_meter("master")["peak"] == pytest.approx(expected, abs=1e-5)
