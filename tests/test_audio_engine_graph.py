"""AudioEngine routing-graph validation (read-only). Engine-only, no UI."""

import copy

import numpy as np
import pytest

from audio_engine import AudioEngine


SR = 8000


def _tone(n, value=0.5):
    return np.full((n, 2), value, dtype=np.float32)


def _snapshot(engine):
    return copy.deepcopy(dict(engine.track_outputs))


def test_valid_acyclic_zero_to_one_validate_succeeds(qapp):
    """Valid acyclic 0→1 + 1→master: validate_graph() succeeds."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.load_audio(1, _tone(64, 0.3))
    engine.set_track_output(0, 1)
    assert engine.get_track_output(0) == 1
    assert engine.get_track_output(1) == "master"
    assert engine.validate_graph() is None
    assert engine.validate_routing() is None

    empty = AudioEngine(sample_rate=SR)
    assert empty.validate_graph() is None

    master_only = AudioEngine(sample_rate=SR)
    master_only.load_audio(0, _tone(64, 0.2))
    master_only.set_track_output(0, "master")
    assert master_only.validate_graph() is None


def test_dangling_dest_raises_graph_unchanged(qapp):
    """Output to track 99 with no live track 99: raises, graph unchanged."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.track_outputs[0] = 99
    before = _snapshot(engine)
    with pytest.raises(ValueError, match="dangling"):
        engine.validate_graph()
    assert engine.track_outputs == before
    assert engine.track_outputs[0] == 99


def test_type_error_dest_stuffed_or_setter_rejects(qapp):
    """Wrong dest types: setter rejects; stuffed graph validate raises, no mutate."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    for bad in ([1, 2], 1.5, True, False, {"x": 1}):
        with pytest.raises(ValueError):
            engine.set_track_output(0, bad)
        assert engine.get_track_output(0) == "master"

    for bad in ([1, 2], 1.5, None, True, False):
        engine.track_outputs[0] = "master"
        engine.track_outputs[0] = bad
        before = _snapshot(engine)
        with pytest.raises(ValueError, match="type error"):
            engine.validate_graph()
        assert engine.track_outputs == before
        assert engine.track_outputs[0] == bad


def test_stale_output_after_unload_invalid_not_mutated(qapp):
    """Unload dest: leftover dest pointing at unloaded track is invalid; no fix."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.load_audio(1, _tone(64, 0.3))
    engine.set_track_output(0, 1)
    engine.unload_track(1)
    # unload clears track 1; dest 0→1 now points at a non-live track
    assert 1 not in engine.track_buffers
    before = _snapshot(engine)
    assert before.get(0) == 1
    with pytest.raises(ValueError):
        engine.validate_graph()
    assert engine.track_outputs == before
    assert engine.track_outputs[0] == 1

    # Leftover source entry after unload of the source itself
    engine2 = AudioEngine(sample_rate=SR)
    engine2.load_audio(0, _tone(64, 0.2))
    engine2.unload_track(0)
    # unload already deletes track_outputs[0]; stuff a leftover
    engine2.track_outputs[0] = "master"
    before2 = _snapshot(engine2)
    with pytest.raises(ValueError, match="stale"):
        engine2.validate_graph()
    assert engine2.track_outputs == before2


def test_stored_cycle_rejected_without_mutating(qapp):
    """Injected 0→1, 1→0 cycle: validate raises; dests unchanged."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.load_audio(1, _tone(64, 0.3))
    engine.track_outputs[0] = 1
    engine.track_outputs[1] = 0
    before = _snapshot(engine)
    with pytest.raises(ValueError, match="cycle"):
        engine.validate_graph()
    assert engine.track_outputs == before
    assert engine.get_track_output(0) == 1
    assert engine.get_track_output(1) == 0


def test_validate_accepts_bus_dest_rejects_ghost_bus(qapp):
    """validate_graph accepts 0→drum when bus exists; rejects 0→ghost."""
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(64, 0.2))
    engine.add_bus("drum")
    engine.set_track_output(0, "drum")
    assert engine.get_track_output(0) == "drum"
    assert engine.validate_graph() is None

    engine.track_outputs[0] = "ghost"
    before = _snapshot(engine)
    with pytest.raises(ValueError, match="dangling"):
        engine.validate_graph()
    assert engine.track_outputs == before
    assert engine.track_outputs[0] == "ghost"
