"""Safe graph rebuilds: unload/remove_bus clean refs; mutations while stopped."""

import numpy as np
import pytest

from audio_engine import AudioEngine
from effects_rack import apply_inserts, clear_test_inserts, set_test_insert


SR = 8000


@pytest.fixture(autouse=True)
def _isolate_test_inserts():
    clear_test_inserts()
    yield
    clear_test_inserts()


def _tone(n, value=0.5):
    return np.full((n, 2), value, dtype=np.float32)


def test_unload_track_that_was_dest_reroutes_to_master(qapp):
    """Unload a dest track: other track output becomes master; graph valid; mix OK."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.load_audio(1, _tone(64, 0.3))
    engine.set_track_output(0, 1)
    assert engine.get_track_output(0) == 1

    engine.unload_track(1)

    assert 1 not in engine.track_buffers
    assert engine.get_track_output(0) == "master"
    assert engine.validate_graph() is None
    mixed = engine.mix()
    assert isinstance(mixed, np.ndarray)
    assert mixed.dtype == np.float32
    assert mixed.shape[1] == 2
    # Track 0 still audible direct to master.
    expected = np.float32(np.tanh(0.2))
    assert np.allclose(mixed, expected, atol=1e-5)


def test_remove_bus_that_was_dest_and_send_cleans_refs(qapp):
    """remove_bus: outputs→master, sends to bus dropped; validate OK."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.25))
    engine.load_audio(1, _tone(64, 0.15))
    engine.add_bus("fx")
    engine.add_bus("drum")
    engine.set_track_output(0, "fx")
    engine.add_send(1, "fx")
    engine.set_bus_output("drum", "fx")
    engine.add_send("drum", "fx")

    engine.remove_bus("fx")

    assert "fx" not in engine.list_buses()
    assert engine.get_track_output(0) == "master"
    assert "fx" not in engine.get_sends(1)
    assert engine.get_bus_output("drum") == "master"
    assert "fx" not in engine.get_sends("drum")
    assert engine.validate_graph() is None
    mixed = engine.mix()
    expected = np.float32(np.tanh(0.25 + 0.15))
    assert np.allclose(mixed, expected, atol=1e-5)


def test_add_bus_twice_same_name_idempotent(qapp):
    """Second add_bus of same name does not duplicate; list_buses unique."""
    engine = AudioEngine(sample_rate=SR)
    engine.add_bus("drum")
    engine.add_bus("drum")
    buses = engine.list_buses()
    assert buses.count("drum") == 1
    assert buses == sorted(set(buses))


def test_reroute_set_track_output_while_sends_exist(qapp):
    """Reroute main dest while sends exist: still valid; send still extra."""
    engine = AudioEngine(sample_rate=SR)
    n = 64
    engine.load_audio(0, _tone(n, 0.2))
    engine.load_audio(1, _tone(n, 0.0))
    engine.add_bus("fx")
    engine.set_track_output(0, 1)
    engine.add_send(0, "fx", level=1.0)
    assert engine.get_sends(0) == ["fx"]

    engine.set_track_output(0, "master")

    assert engine.get_track_output(0) == "master"
    assert engine.get_sends(0) == ["fx"]
    assert engine.validate_graph() is None
    mixed = engine.mix()
    # Main 0.2 + send 0.2 via fx → master
    expected = np.float32(np.tanh(0.2 + 0.2))
    assert np.allclose(mixed, expected, atol=1e-5)


def test_cycle_still_rejected_after_rebuilds(qapp):
    """Cycle rejection survives unload/remove/add rebuild sequence."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(32, 0.1))
    engine.load_audio(1, _tone(32, 0.1))
    engine.add_bus("a")
    engine.add_bus("b")
    engine.set_track_output(0, 1)
    engine.unload_track(1)
    engine.load_audio(1, _tone(32, 0.1))
    engine.set_track_output(0, 1)
    with pytest.raises(ValueError, match="cycle"):
        engine.set_track_output(1, 0)
    engine.remove_bus("a")
    engine.add_bus("a")
    engine.set_track_output(0, "a")
    engine.set_bus_output("a", "b")
    with pytest.raises(ValueError, match="cycle"):
        engine.set_bus_output("b", "a")
    assert engine.validate_graph() is None


def test_unload_track_clears_insert_registration(qapp):
    """Unload clears channel inserts and test-insert hook; dry mix still OK."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.4))
    engine.set_inserts(0, [{"type": "gain", "gain": 0.5}])
    set_test_insert(0, gain=0.5)
    assert engine.get_inserts(0)[0]["type"] == "gain"
    # Confirm hook is live before unload
    assert apply_inserts(0, np.ones((4, 2), dtype=np.float32))[0, 0] == pytest.approx(0.5)

    engine.unload_track(0)

    assert engine.get_inserts(0) == []
    # Test hook cleared → dry identity
    raw = np.ones((4, 2), dtype=np.float32)
    assert apply_inserts(0, raw) is raw

    engine.load_audio(0, _tone(64, 0.4))
    mixed = engine.mix()
    expected = np.float32(np.tanh(0.4))
    assert np.allclose(mixed, expected, atol=1e-5)


def test_get_state_set_state_track_outputs_schema_compat(qapp):
    """get_state/set_state round-trip for track_outputs (schema 1.1 additive)."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(32, 0.2))
    engine.load_audio(1, _tone(32, 0.3))
    engine.add_bus("drum")
    engine.set_track_output(0, "drum")
    engine.set_track_output(1, 0)
    engine.add_send(0, "drum")  # session-only; must not appear in get_state

    state = engine.get_state()
    assert "track_outputs" in state
    assert state["track_outputs"][0] == "drum"
    assert state["track_outputs"][1] == 0
    # Engine get_state stays M1-shaped: no buses/sends/inserts keys.
    assert "buses" not in state
    assert "track_sends" not in state
    assert "inserts" not in state

    engine2 = AudioEngine(sample_rate=SR)
    engine2.add_bus("drum")  # buses still applied by ProjectManager, not get_state
    engine2.set_state(state)
    assert engine2.get_track_output(0) == "drum"
    assert engine2.get_track_output(1) == 0
    assert engine2.validate_graph() is None


def test_unload_and_remove_bus_reject_while_playing(qapp):
    """Destructive rebuilds raise if transport is playing."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(32, 0.2))
    engine.add_bus("fx")
    engine.is_playing = True
    with pytest.raises(RuntimeError, match="stop transport before graph rebuild"):
        engine.unload_track(0)
    with pytest.raises(RuntimeError, match="stop transport before graph rebuild"):
        engine.remove_bus("fx")
    engine.is_playing = False
    engine.is_paused = True
    with pytest.raises(RuntimeError, match="stop transport before graph rebuild"):
        engine.clear()
    engine.is_paused = False
    engine.unload_track(0)
    engine.remove_bus("fx")
    assert engine.validate_graph() is None


def test_remove_bus_idempotent_missing(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.remove_bus("ghost")  # no-op
    engine.add_bus("fx")
    engine.remove_bus("fx")
    engine.remove_bus("fx")
    assert "fx" not in engine.list_buses()


def test_rebuild_graph_validates_only(qapp):
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(16, 0.1))
    assert engine.rebuild_graph() is None
    engine.track_outputs[0] = 99
    with pytest.raises(ValueError, match="dangling"):
        engine.rebuild_graph()
