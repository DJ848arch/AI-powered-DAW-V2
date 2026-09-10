"""On-channel insert/routing boundary. Identity DSP; no plugin hosting."""

import numpy as np
import pytest

from audio_engine import AudioEngine
from effects_rack import apply_inserts, clear_test_inserts, set_test_insert


SR = 8000


def _tone(n, value=0.5):
    return np.full((n, 2), value, dtype=np.float32)


def _assert_stereo_float32(mix):
    assert isinstance(mix, np.ndarray)
    assert mix.dtype == np.float32
    assert mix.ndim == 2
    assert mix.shape[1] == 2


@pytest.fixture(autouse=True)
def _isolate_test_inserts():
    clear_test_inserts()
    yield
    clear_test_inserts()


def test_dry_regression_no_inserts_matches_pre_insert_mix(qapp):
    """Empty/placeholder rack: mix equals today's mix (identity apply_inserts)."""
    amp = 0.4
    n = SR
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(n, amp))
    assert engine._insert_processor is None
    mixed = engine.mix()
    _assert_stereo_float32(mixed)
    expected = np.float32(np.tanh(amp))
    assert np.allclose(mixed, expected, atol=1e-5)

    # Explicit identity hook must not change the sound.
    identity = AudioEngine(sample_rate=SR)
    identity.load_audio(0, _tone(n, amp))
    identity._insert_processor = lambda tid, audio: audio
    with_hook = identity.mix()
    assert np.allclose(with_hook, mixed, atol=1e-6)
    assert np.allclose(with_hook, expected, atol=1e-5)

    # Module-level apply_inserts is dry when nothing is configured.
    raw = _tone(32, 0.3)
    assert apply_inserts(0, raw) is raw


def test_inserts_before_split_scale_main_and_sends(qapp):
    """Fake insert gain 0.5 on track 0: both direct and send paths scaled."""
    amp = 0.4
    n = SR
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(n, amp))
    engine.add_bus("fx")
    engine.add_send(0, "fx", level=1.0)
    assert engine.get_track_output(0) == "master"

    without = engine.mix()
    expected_both = np.float32(np.tanh(amp + amp))
    assert np.allclose(without, expected_both, atol=1e-5)

    set_test_insert(0, gain=0.5)
    scaled = engine.mix()
    _assert_stereo_float32(scaled)
    # Inserts before split: 0.4 * 0.5 on both main and send.
    expected_scaled = np.float32(np.tanh(amp * 0.5 + amp * 0.5))
    assert np.allclose(scaled, expected_scaled, atol=1e-5)

    # Mute after inserts silences both paths.
    engine.set_track_mute(0, True)
    muted = engine.mix()
    assert np.max(np.abs(muted)) < 1e-6


def test_inserts_are_on_channel_not_on_bus_or_other_tracks(qapp):
    """Fake insert on track 0 does not process track 1 (inserts are not on the bus)."""
    n = SR
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(n, 0.4))
    engine.load_audio(1, _tone(n, 0.3))
    engine.add_bus("fx")
    engine.set_track_output(1, "fx")

    set_test_insert(0, gain=0.5)
    mixed = engine.mix()
    _assert_stereo_float32(mixed)
    # Track 0 halved on its channel; track 1 (via bus) unchanged.
    expected = np.float32(np.tanh(0.4 * 0.5 + 0.3))
    assert np.allclose(mixed, expected, atol=1e-5)

    # If the insert leaked onto track 1 / the bus, energy would be tanh(0.2+0.15).
    leaked = np.float32(np.tanh(0.4 * 0.5 + 0.3 * 0.5))
    assert not np.allclose(mixed, leaked, atol=1e-5)


def test_engine_insert_processor_hook_characterizes_order(qapp):
    """engine._insert_processor also runs on-channel before fader/split."""
    n = SR
    amp = 0.4
    engine = AudioEngine(sample_rate=SR)
    engine.load_audio(0, _tone(n, amp))
    engine.add_bus("fx")
    engine.add_send(0, "fx")

    engine._insert_processor = lambda tid, audio: audio * 0.5 if tid == 0 else audio
    mixed = engine.mix()
    expected = np.float32(np.tanh(amp * 0.5 + amp * 0.5))
    assert np.allclose(mixed, expected, atol=1e-5)
