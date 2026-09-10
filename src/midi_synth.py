"""Simple oscillator / drum-sample MIDI synth (numpy only).

Renders a list of MIDI notes to a float32 audio buffer so Play can
sound notes without FluidSynth or other heavy backends.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np


__all__ = ["render_midi"]

# Seconds of extra silence after the last note-off so decaying
# instruments (piano) can release without a click.
_TAIL_SECONDS = 0.12

# Per-note gain so a few overlapping notes stay inside [-1, 1].
_NOTE_GAIN = 0.38

# Drum GM map (channel-10 style). Anything else is tuned percussion.
_KICK_PITCHES = frozenset({35, 36})
_SNARE_PITCHES = frozenset({37, 38, 39, 40})
_HAT_CLOSED_PITCHES = frozenset({42, 44})
_HAT_OPEN_PITCHES = frozenset({46})
_CRASH_PITCHES = frozenset({49, 57})

_ALIASES = {
    "piano": "piano",
    "acoustic_piano": "piano",
    "acoustic piano": "piano",
    "keys": "piano",
    "electric_piano": "piano",
    "bass": "bass",
    "bass_synth": "bass",
    "synth_bass": "bass",
    "synth bass": "bass",
    "drums": "drums",
    "drum": "drums",
    "kit": "drums",
    "percussion": "drums",
    "lead": "lead",
    "lead_synth": "lead",
    "synth": "lead",
    "synth_lead": "lead",
    "saw": "lead",
}


def render_midi(
    notes,
    instrument="piano",
    bpm=120,
    sample_rate=44100,
    channels=2,
) -> np.ndarray:
    """Render MIDI notes to a float32 audio buffer.

    Parameters
    ----------
    notes : list of dict
        Each dict has pitch (MIDI int), start_beat, duration_beats,
        and velocity (1-127). Missing / 0 velocity is silent.
    instrument : str
        One of piano, bass, drums, lead. Unknown names fall back to piano.
    bpm : float
        Tempo used to convert beats to seconds.
    sample_rate : int
        Output sample rate in Hz.
    channels : int
        2 → shape (n, 2) stereo; 1 → shape (n,) mono.

    Returns
    -------
    np.ndarray
        dtype float32, roughly in [-1, 1].
    """
    sr = int(sample_rate) if sample_rate and int(sample_rate) > 0 else 44100
    ch = int(channels) if channels else 2
    tempo = float(bpm) if bpm and float(bpm) > 0 else 120.0
    kind = _normalize_instrument(instrument)

    note_list = list(notes) if notes else []
    seconds_per_beat = 60.0 / tempo

    end_time = 0.0
    parsed: List[Dict[str, Any]] = []
    for raw in note_list:
        parsed_note = _parse_note(raw)
        if parsed_note is None:
            continue
        note_end = (
            parsed_note["start_beat"] + parsed_note["duration_beats"]
        ) * seconds_per_beat
        if note_end > end_time:
            end_time = note_end
        parsed.append(parsed_note)

    n_samples = int(np.ceil(end_time * sr)) + int(round(_TAIL_SECONDS * sr))
    if n_samples < 1:
        n_samples = 1

    mix = np.zeros(n_samples, dtype=np.float64)

    for note in parsed:
        start_s = note["start_beat"] * seconds_per_beat
        dur_s = note["duration_beats"] * seconds_per_beat
        start_i = int(round(start_s * sr))
        if start_i >= n_samples:
            continue

        wave = _synth_note(
            kind=kind,
            pitch=note["pitch"],
            duration_s=dur_s,
            velocity=note["velocity"],
            sample_rate=sr,
        )
        if wave.size == 0:
            continue

        if start_i < 0:
            wave = wave[-start_i:]
            start_i = 0
        end_i = start_i + int(wave.size)
        if end_i > n_samples:
            wave = wave[: n_samples - start_i]
            end_i = n_samples
        if wave.size == 0 or start_i >= n_samples:
            continue
        mix[start_i:end_i] += wave

    mix = np.clip(mix, -1.0, 1.0).astype(np.float32, copy=False)
    return _to_channels(mix, ch)


def _normalize_instrument(instrument: Optional[str]) -> str:
    if instrument is None:
        return "piano"
    key = str(instrument).strip().lower().replace("-", "_")
    return _ALIASES.get(key, "piano")


def _field(raw: Any, key: str, default=None):
    """Read a dict key or object attribute."""
    if isinstance(raw, dict):
        return raw.get(key, default)
    if hasattr(raw, "to_dict"):
        try:
            return raw.to_dict().get(key, default)
        except Exception:
            pass
    return getattr(raw, key, default)


def _parse_note(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if not isinstance(raw, dict) and not hasattr(raw, "pitch"):
        return None
    try:
        pitch = int(_field(raw, "pitch", 60))
    except (TypeError, ValueError):
        pitch = 60
    pitch = int(np.clip(pitch, 0, 127))

    try:
        start_beat = float(_field(raw, "start_beat", 0.0))
    except (TypeError, ValueError):
        start_beat = 0.0
    if not np.isfinite(start_beat):
        start_beat = 0.0
    start_beat = max(0.0, start_beat)

    try:
        duration_beats = float(_field(raw, "duration_beats", 0.0))
    except (TypeError, ValueError):
        duration_beats = 0.0
    if not np.isfinite(duration_beats) or duration_beats <= 0.0:
        return None

    vel_raw = _field(raw, "velocity", None)
    if vel_raw is None:
        velocity = 0
    else:
        try:
            velocity = int(vel_raw)
        except (TypeError, ValueError):
            velocity = 0
    if velocity <= 0:
        velocity = 0
    else:
        velocity = int(np.clip(velocity, 1, 127))

    return {
        "pitch": pitch,
        "start_beat": start_beat,
        "duration_beats": duration_beats,
        "velocity": velocity,
    }


def _velocity_amp(velocity: int) -> float:
    """Linear 0..1. velocity 0 / missing → silent."""
    if velocity <= 0:
        return 0.0
    return float(velocity) / 127.0


def _midi_to_hz(pitch: int) -> float:
    return float(440.0 * (2.0 ** ((float(pitch) - 69.0) / 12.0)))


def _synth_note(
    kind: str,
    pitch: int,
    duration_s: float,
    velocity: int,
    sample_rate: int,
) -> np.ndarray:
    amp = _velocity_amp(velocity) * _NOTE_GAIN
    if amp <= 0.0 or duration_s <= 0.0:
        return np.zeros(0, dtype=np.float64)

    if kind == "drums":
        return _synth_drum(pitch, duration_s, amp, sample_rate)
    if kind == "bass":
        return _synth_bass(pitch, duration_s, amp, sample_rate)
    if kind == "lead":
        return _synth_lead(pitch, duration_s, amp, sample_rate)
    return _synth_piano(pitch, duration_s, amp, sample_rate)


def _time_axis(n: int, sample_rate: int) -> np.ndarray:
    return np.arange(n, dtype=np.float64) / float(sample_rate)


def _apply_release(env: np.ndarray, n_on: int, sample_rate: int, release_s: float) -> np.ndarray:
    """Fade from the note-off sample to zero over release_s (no click)."""
    n = int(env.size)
    n_on = max(0, min(int(n_on), n))
    n_rel = max(1, int(round(release_s * sample_rate)))
    if n_on >= n:
        # Still taper the last few samples.
        n_rel = min(n_rel, n)
        if n_rel > 0:
            env[n - n_rel :] *= np.linspace(1.0, 0.0, n_rel, dtype=np.float64)
        return env
    tail = env[n_on - 1] if n_on > 0 else 0.0
    n_rel = min(n_rel, n - n_on)
    if n_rel > 0 and tail != 0.0:
        env[n_on : n_on + n_rel] = tail * np.linspace(1.0, 0.0, n_rel, dtype=np.float64)
    if n_on + n_rel < n:
        env[n_on + n_rel :] = 0.0
    return env


def _adsr_decay(
    n: int,
    n_on: int,
    sample_rate: int,
    attack_s: float,
    decay_tau: float,
    release_s: float,
    sustain: float = 0.0,
) -> np.ndarray:
    """Attack, exponential decay toward `sustain`, then linear release."""
    t = _time_axis(n, sample_rate)
    attack_s = max(attack_s, 1.0 / sample_rate)
    attack = 1.0 - np.exp(-t / attack_s)
    # Fast attack saturates near 1; multiply so we don't overshoot badly.
    attack = np.minimum(attack, 1.0)
    decay = sustain + (1.0 - sustain) * np.exp(-t / max(decay_tau, 1e-4))
    env = attack * decay
    return _apply_release(env, n_on, sample_rate, release_s)


def _note_lengths(duration_s: float, sample_rate: int, release_s: float) -> tuple:
    n_on = max(1, int(round(duration_s * sample_rate)))
    n_rel = max(1, int(round(release_s * sample_rate)))
    n = n_on + n_rel
    return n, n_on


def _synth_piano(pitch: int, duration_s: float, amp: float, sample_rate: int) -> np.ndarray:
    """Decaying harmonic tone: partials 1,2,3,4,6 + exponential decay."""
    release_s = 0.045
    n, n_on = _note_lengths(duration_s, sample_rate, release_s)
    t = _time_axis(n, sample_rate)
    freq = _midi_to_hz(pitch)
    # Higher notes decay faster (shorter strings).
    decay_tau = 0.55 * (0.45 + 50.0 / max(float(pitch), 20.0))
    w = 2.0 * np.pi * freq * t
    wave = (
        1.00 * np.sin(w)
        + 0.50 * np.sin(2.0 * w)
        + 0.28 * np.sin(3.0 * w)
        + 0.16 * np.sin(4.0 * w)
        + 0.08 * np.sin(6.0 * w)
    )
    wave /= 2.02  # sum of harmonic weights
    env = _adsr_decay(
        n, n_on, sample_rate,
        attack_s=0.003,
        decay_tau=decay_tau,
        release_s=release_s,
        sustain=0.04,
    )
    return (amp * env * wave).astype(np.float64, copy=False)


def _synth_bass(pitch: int, duration_s: float, amp: float, sample_rate: int) -> np.ndarray:
    """Low, round: sine + sub-octave + soft triangle, slower attack."""
    release_s = 0.06
    n, n_on = _note_lengths(duration_s, sample_rate, release_s)
    t = _time_axis(n, sample_rate)
    freq = _midi_to_hz(pitch)
    # Keep the written pitch but add a sub so energy sits low.
    fund = np.sin(2.0 * np.pi * freq * t)
    sub = np.sin(2.0 * np.pi * (freq * 0.5) * t)
    phase = t * freq
    tri = 2.0 * np.abs(2.0 * np.mod(phase, 1.0) - 1.0) - 1.0
    wave = 0.62 * fund + 0.48 * sub + 0.12 * tri
    wave /= 1.22
    env = _adsr_decay(
        n, n_on, sample_rate,
        attack_s=0.022,
        decay_tau=1.15,
        release_s=release_s,
        sustain=0.18,
    )
    return (amp * 1.15 * env * wave).astype(np.float64, copy=False)


def _synth_lead(pitch: int, duration_s: float, amp: float, sample_rate: int) -> np.ndarray:
    """Bright sustained saw (+ a little square), much less decay than piano."""
    release_s = 0.05
    n, n_on = _note_lengths(duration_s, sample_rate, release_s)
    t = _time_axis(n, sample_rate)
    freq = _midi_to_hz(pitch)
    phase = t * freq
    saw = 2.0 * np.mod(phase, 1.0) - 1.0
    square = np.where(np.mod(phase, 1.0) < 0.5, 1.0, -1.0)
    wave = 0.78 * saw + 0.22 * square
    env = _adsr_decay(
        n, n_on, sample_rate,
        attack_s=0.007,
        decay_tau=2.4,
        release_s=release_s,
        sustain=0.72,
    )
    return (amp * 0.85 * env * wave).astype(np.float64, copy=False)


def _synth_drum(pitch: int, duration_s: float, amp: float, sample_rate: int) -> np.ndarray:
    """Short noise / click / thump. GM kit pitches, else tuned percussion."""
    if pitch in _KICK_PITCHES:
        return _drum_kick(duration_s, amp, sample_rate)
    if pitch in _SNARE_PITCHES:
        return _drum_snare(duration_s, amp, sample_rate, seed=pitch)
    if pitch in _HAT_CLOSED_PITCHES:
        return _drum_hat(duration_s, amp, sample_rate, open_hat=False, seed=pitch)
    if pitch in _HAT_OPEN_PITCHES:
        return _drum_hat(duration_s, amp, sample_rate, open_hat=True, seed=pitch)
    if pitch in _CRASH_PITCHES:
        return _drum_crash(duration_s, amp, sample_rate, seed=pitch)
    return _drum_tuned(pitch, duration_s, amp, sample_rate)


def _drum_n(duration_s: float, natural_s: float, sample_rate: int) -> int:
    """Drums are short: cap at the instrument's natural length, honor shorter notes."""
    dur = min(max(float(duration_s), 0.0), float(natural_s))
    n = int(round(dur * sample_rate))
    return max(n, 1)


def _fade_edges(wave: np.ndarray, sample_rate: int, fade_s: float = 0.002) -> np.ndarray:
    n = int(wave.size)
    n_fade = max(1, min(n // 2, int(round(fade_s * sample_rate))))
    if n_fade > 0:
        ramp = np.linspace(0.0, 1.0, n_fade, dtype=np.float64)
        wave[:n_fade] *= ramp
        wave[-n_fade:] *= ramp[::-1]
    return wave


def _drum_kick(duration_s: float, amp: float, sample_rate: int) -> np.ndarray:
    n = _drum_n(duration_s, 0.22, sample_rate)
    t = _time_axis(n, sample_rate)
    # Pitch sweep ~150 Hz → 40 Hz (classic analog kick).
    freq = 40.0 + 110.0 * np.exp(-t / 0.028)
    phase = np.cumsum(2.0 * np.pi * freq / sample_rate)
    body = np.sin(phase) * np.exp(-t / 0.09)
    click = np.sin(2.0 * np.pi * 1800.0 * t) * np.exp(-t / 0.004) * 0.25
    wave = body + click
    return _fade_edges(amp * 1.35 * wave, sample_rate)


def _drum_snare(duration_s: float, amp: float, sample_rate: int, seed: int) -> np.ndarray:
    n = _drum_n(duration_s, 0.20, sample_rate)
    t = _time_axis(n, sample_rate)
    rng = np.random.RandomState(10_000 + int(seed))
    tone = np.sin(2.0 * np.pi * 190.0 * t) * np.exp(-t / 0.045)
    noise = rng.randn(n).astype(np.float64) * np.exp(-t / 0.07)
    wave = 0.35 * tone + 0.80 * noise
    return _fade_edges(amp * 1.05 * wave, sample_rate)


def _drum_hat(
    duration_s: float,
    amp: float,
    sample_rate: int,
    open_hat: bool,
    seed: int,
) -> np.ndarray:
    natural = 0.22 if open_hat else 0.055
    n = _drum_n(duration_s, natural, sample_rate)
    t = _time_axis(n, sample_rate)
    rng = np.random.RandomState(20_000 + int(seed) + (1 if open_hat else 0))
    noise = rng.randn(n).astype(np.float64)
    # Crude high-pass so hats are airy, not a thump.
    hp = np.empty_like(noise)
    hp[0] = noise[0]
    hp[1:] = noise[1:] - noise[:-1]
    tau = 0.085 if open_hat else 0.018
    wave = hp * np.exp(-t / tau)
    peak = np.max(np.abs(wave)) or 1.0
    wave = wave / peak
    return _fade_edges(amp * 0.85 * wave, sample_rate, fade_s=0.001)


def _drum_crash(duration_s: float, amp: float, sample_rate: int, seed: int) -> np.ndarray:
    n = _drum_n(duration_s, 0.28, sample_rate)
    t = _time_axis(n, sample_rate)
    rng = np.random.RandomState(30_000 + int(seed))
    noise = rng.randn(n).astype(np.float64)
    hp = np.empty_like(noise)
    hp[0] = noise[0]
    hp[1:] = noise[1:] - 0.85 * noise[:-1]
    wave = hp * np.exp(-t / 0.16)
    peak = np.max(np.abs(wave)) or 1.0
    return _fade_edges(amp * 0.9 * wave / peak, sample_rate)


def _drum_tuned(pitch: int, duration_s: float, amp: float, sample_rate: int) -> np.ndarray:
    """Non-kit pitch: short decaying tone + noise click (not a sustained osc)."""
    n = _drum_n(duration_s, 0.16, sample_rate)
    t = _time_axis(n, sample_rate)
    freq = _midi_to_hz(pitch)
    rng = np.random.RandomState(40_000 + int(pitch))
    tone = np.sin(2.0 * np.pi * freq * t) * np.exp(-t / 0.07)
    click = rng.randn(n).astype(np.float64) * np.exp(-t / 0.012)
    wave = 0.70 * tone + 0.45 * click
    return _fade_edges(amp * wave, sample_rate)


def _to_channels(mono: np.ndarray, channels: int) -> np.ndarray:
    mono = np.asarray(mono, dtype=np.float32)
    if channels <= 1:
        return mono
    # Duplicate to N channels (default stereo). Same signal L/R.
    return np.column_stack([mono] * channels).astype(np.float32, copy=False)

