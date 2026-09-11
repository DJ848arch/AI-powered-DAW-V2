"""
Audio Engine with Playback Controls
Handles audio playback, mixing, and routing.

WAV clips are loaded, trimmed, and mixed honoring each clip's timeline
start (and trim/length). Playback works through sounddevice when a
device is present, and through an offline render path otherwise so
tests can verify samples without hardware.
"""

import math
import os
import threading
import queue
import time
import wave
from pathlib import Path
from typing import Optional, List, Dict, Callable, Any, Iterable, Union

import numpy as np

try:
    from effects_rack import apply_inserts as _effects_apply_inserts
    from effects_rack import apply_insert_chain as _effects_apply_insert_chain
    from effects_rack import clear_test_insert as _effects_clear_test_insert
except Exception:
    def _effects_apply_inserts(track_id, audio):
        """Identity fallback when the effects rack is unavailable."""
        return audio

    def _effects_apply_insert_chain(audio, slots):
        """Identity fallback when the effects rack is unavailable."""
        return audio

    def _effects_clear_test_insert(track_id):
        """No-op fallback when the effects rack is unavailable."""
        return

try:
    import soundfile as sf
    SF_AVAILABLE = True
except Exception:
    sf = None
    SF_AVAILABLE = False

try:
    import sounddevice as sd
    SD_AVAILABLE = True
except Exception:
    sd = None
    SD_AVAILABLE = False

try:
    from PyQt6.QtCore import QObject, pyqtSignal, QTimer
    QT_AVAILABLE = True
except Exception:
    QT_AVAILABLE = False

    class QObject:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

    class _DummySignal:
        def emit(self, *args, **kwargs):
            pass

        def connect(self, *args, **kwargs):
            pass

    def pyqtSignal(*args, **kwargs):  # type: ignore
        return _DummySignal()

    class QTimer:  # type: ignore
        def __init__(self, *args, **kwargs):
            self.timeout = _DummySignal()

        def setInterval(self, *args, **kwargs):
            pass

        def start(self, *args, **kwargs):
            pass

        def stop(self):
            pass


# Clip field aliases (clip.py + common QA / inspector names)
_START_KEYS = (
    "start_time", "start", "offset", "start_offset",
    "timeline_start", "position", "clip_start",
)
_START_SAMPLE_KEYS = ("start_sample", "start_samples", "sample_offset")
_TRIM_START_KEYS = (
    "trim_start", "trim", "in_point", "source_start",
    "offset_in", "clip_in", "in",
)
_TRIM_END_KEYS = (
    "trim_end", "out_point", "source_end", "clip_out", "out",
)
_LENGTH_KEYS = ("length", "duration", "trim_length", "clip_length")
_PATH_KEYS = (
    "file_path", "path", "file", "filename", "wav",
    "audio_path", "source", "filepath",
)
_AUDIO_KEYS = ("audio_data", "audio", "samples", "data", "buffer")
_TRACK_KEYS = ("track_id", "track", "trackId")
_SR_KEYS = ("sample_rate", "samplerate", "sr")
_ID_KEYS = ("id", "clip_id", "name")


def _first_attr(obj: Any, keys: Iterable[str], default=None):
    """Get the first present attribute or mapping key from obj."""
    for key in keys:
        if isinstance(obj, dict):
            if key in obj and obj[key] is not None:
                return obj[key]
        else:
            if hasattr(obj, key):
                val = getattr(obj, key)
                if val is not None:
                    return val
    return default


def _as_float(value, default=0.0) -> float:
    if value is None:
        return float(default)
    if isinstance(value, (tuple, list)) and value:
        value = value[0]
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_optional_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ensure_stereo(audio_data: np.ndarray) -> np.ndarray:
    """Return float32 stereo (N, 2) audio."""
    data = np.asarray(audio_data)
    if data.size == 0:
        return np.zeros((0, 2), dtype=np.float32)
    if data.ndim == 1:
        data = np.column_stack((data, data))
    elif data.ndim > 1 and data.shape[1] == 1:
        data = np.column_stack((data[:, 0], data[:, 0]))
    elif data.ndim > 1 and data.shape[1] > 2:
        data = data[:, :2]
    return data.astype(np.float32, copy=False)


def read_wav(path: Union[str, Path]):
    """Load a WAV (or any soundfile-supported) clip as (stereo float32, sr)."""
    path = os.fspath(path)
    if SF_AVAILABLE:
        data, sr = sf.read(path, dtype="float32", always_2d=True)
        return ensure_stereo(data), int(sr)

    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)

    if sw == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sw == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 3:
        a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        ints = (
            a[:, 0].astype(np.int32)
            | (a[:, 1].astype(np.int32) << 8)
            | (a[:, 2].astype(np.int32) << 16)
        )
        ints = np.where(ints & 0x800000, ints - 0x1000000, ints)
        data = ints.astype(np.float32) / 8388608.0
    elif sw == 4:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sw}")

    if nch > 1:
        data = data.reshape(-1, nch)
    return ensure_stereo(data), int(sr)


def resample_audio(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Linear resample to dst_sr. Identity if rates match."""
    if src_sr == dst_sr or audio is None or len(audio) == 0:
        return audio
    src_sr = int(src_sr)
    dst_sr = int(dst_sr)
    if src_sr <= 0 or dst_sr <= 0:
        return audio
    n = max(1, int(round(len(audio) * float(dst_sr) / float(src_sr))))
    x = np.linspace(0.0, 1.0, len(audio), endpoint=True)
    xi = np.linspace(0.0, 1.0, n, endpoint=True)
    audio = ensure_stereo(audio)
    cols = [
        np.interp(xi, x, audio[:, c]).astype(np.float32)
        for c in range(audio.shape[1])
    ]
    return np.column_stack(cols)


def apply_trim(
    audio: np.ndarray,
    sample_rate: int,
    trim_start: float = 0.0,
    trim_end: float = 0.0,
    length: Optional[float] = None,
) -> np.ndarray:
    """Slice audio by trim_start / trim_end / length (all in seconds).

    trim_end <= 0 means 'through the end of the source' (clip.py convention).
    length, if set, caps the duration of the already-trimmed region.
    """
    audio = ensure_stereo(audio)
    if len(audio) == 0:
        return audio

    start_s = int(round(max(0.0, _as_float(trim_start, 0.0)) * sample_rate))
    if trim_end is not None and _as_float(trim_end, 0.0) > 0:
        end_s = int(round(_as_float(trim_end) * sample_rate))
    else:
        end_s = len(audio)

    start_s = max(0, min(start_s, len(audio)))
    end_s = max(start_s, min(end_s, len(audio)))
    sliced = audio[start_s:end_s]

    if length is not None and _as_float(length, 0.0) > 0:
        n = int(round(_as_float(length) * sample_rate))
        if n < len(sliced):
            sliced = sliced[: max(0, n)]
    return sliced


def apply_pan(segment: np.ndarray, pan: float) -> np.ndarray:
    """Constant-power-ish linear pan. -1 full left, 0 center, 1 full right."""
    segment = ensure_stereo(segment)
    if abs(pan) < 1e-12:
        return segment
    left_gain = min(1.0, 1.0 - pan)
    right_gain = min(1.0, 1.0 + pan)
    out = segment.copy()
    out[:, 0] *= left_gain
    out[:, 1] *= right_gain
    return out


def mix_clips(
    clips: Iterable[Any],
    sample_rate: int = 44100,
    channels: int = 2,
    start_time: float = 0.0,
    end_time: Optional[float] = None,
) -> np.ndarray:
    """Mix clip-like objects/dicts into a stereo buffer, honoring start/trim.

    This is the inspector fix: each clip is placed at its timeline start
    (not sample 0). Trim/length crop the source before placement.
    """
    engine = AudioEngine(sample_rate=sample_rate)
    engine.channels = channels
    records = []
    for clip in clips or []:
        rec = engine._clip_to_record(clip, default_track=0)
        if rec is not None:
            records.append(rec)
    return engine._mix_records(
        records, start_time=start_time, end_time=end_time
    )


class AudioEngine(QObject):
    """Main audio engine for playback and mixing."""

    playback_started = pyqtSignal()
    playback_paused = pyqtSignal()
    playback_stopped = pyqtSignal()
    playback_position_changed = pyqtSignal(float)
    playback_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, sample_rate=44100, buffer_size=1024):
        super().__init__()

        self.sample_rate = int(sample_rate)
        self.buffer_size = int(buffer_size)
        self.channels = 2

        # Playback state
        self.is_playing = False
        self.is_paused = False
        self.current_position = 0.0  # seconds
        self.start_position = 0.0
        self._offline_mode = False

        # Audio data
        self.master_mix = None  # Mixed audio buffer (timeline-aligned)
        self.track_buffers = {}  # track_id: timeline-aligned audio_data
        self.clips: List[Dict[str, Any]] = []  # placed clip records
        self._clip_seq = 0

        # Track settings
        self.track_volumes = {}  # track_id: volume (0.0 - 1.0)
        self.track_pans = {}     # track_id: pan (-1.0 to 1.0)
        self.track_mutes = {}    # track_id: muted
        self.track_solos = {}    # track_id: soloed
        self.track_outputs = {}  # track_id: "master", dest track id (int), or bus name
        self._buses = set()      # named mix buses; persisted by ProjectManager
        self.track_sends = {}    # track_id: list of extra dests (bus name or live track id)
        self.track_send_levels = {}  # track_id: {dest: finite non-negative gain}; default 1.0
        self.track_send_modes = {}   # track_id: {dest: "pre"|"post"}; default "post"
        # Ordered insert slots: int track id or bus name → list of dicts. [] = dry.
        self.channel_inserts = {}
        # Bus mixer (defaults: vol 1.0, pan 0.0, dest master)
        self.bus_volumes = {}
        self.bus_pans = {}
        self.bus_outputs = {}
        self.bus_sends = {}
        self.bus_send_levels = {}
        self.bus_send_modes = {}
        # Optional test hook: callable(track_id, audio) -> audio. None = use rack apply_inserts.
        self._insert_processor = None
        # Last-mix peak/rms. Engine data only — no mixer UI this slice.
        self._meters = {
            "tracks": {},
            "buses": {},
            "master": {"peak": 0.0, "rms": 0.0},
        }

        # Audio stream
        self.stream = None
        self.audio_queue = queue.Queue()
        self.audio_thread = None
        self._offline_thread = None
        self._stop_event = threading.Event()
        self._play_lock = threading.RLock()

        # Callbacks
        self.position_callbacks = []

        # Timer for UI updates
        self.update_timer = QTimer()
        try:
            self.update_timer.timeout.connect(self._update_position)
            self.update_timer.setInterval(50)  # 20 FPS
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self):
        """Initialize audio engine. Offline mode is still success."""
        try:
            if SD_AVAILABLE:
                devices = sd.query_devices()
                default_output = sd.query_devices(kind="output")
                print(f"Audio engine initialized: {default_output['name']}")
                self._offline_mode = False
                return True
        except Exception as e:
            self._offline_mode = True
            print(f"Audio engine offline (no device): {e}")
            return True
        self._offline_mode = True
        print("Audio engine initialized in offline render mode")
        return True

    def has_audio_device(self) -> bool:
        """True if a PortAudio output device can be queried."""
        if not SD_AVAILABLE:
            return False
        try:
            sd.query_devices(kind="output")
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_audio(self, track_id=None, audio_data=None, **kwargs):
        """Load audio for a track or clip.

        Accepted forms (all work):
          load_audio(track_id, ndarray)
          load_audio(track_id, "/path/to/clip.wav")
          load_audio("/path/to/clip.wav")
          load_audio(clip_object_or_dict)
          load_audio([clip, clip, ...])
          load_audio(..., start=1.0, trim=0.2, length=1.5)

        Clip start/trim/length are honored. ``start`` is the timeline
        position in seconds (aliases: start_time, offset). ``trim`` /
        ``trim_start`` skip source seconds; ``trim_end`` / ``length``
        cap the source region.
        """
        # List of clips
        if isinstance(track_id, (list, tuple)) and audio_data is None:
            loaded = [self.load_audio(item, **kwargs) for item in track_id]
            return loaded

        # kwargs-only path / explicit path=
        path_kw = kwargs.get("path") or kwargs.get("file_path") or kwargs.get("file")
        if track_id is None and audio_data is None and path_kw:
            return self._load_one(path_kw, **kwargs)

        # First positional is a filesystem path
        if audio_data is None and self._looks_like_path(track_id):
            return self._load_one(track_id, **kwargs)

        # First positional is a clip-like object (dict / AudioClip)
        if audio_data is None and self._looks_like_clip(track_id):
            return self._load_one(track_id, **kwargs)

        # First positional is raw samples
        if audio_data is None and isinstance(track_id, np.ndarray):
            kwargs.setdefault("track_id", 0)
            return self._load_one(track_id, **kwargs)

        # track_id + path
        if self._looks_like_path(audio_data):
            kwargs["track_id"] = self._coerce_track_id(track_id, kwargs)
            return self._load_one(audio_data, **kwargs)

        # track_id + clip-like
        if self._looks_like_clip(audio_data):
            kwargs["track_id"] = self._coerce_track_id(track_id, kwargs)
            return self._load_one(audio_data, **kwargs)

        # Classic: load_audio(track_id, ndarray)
        if audio_data is not None:
            kwargs["track_id"] = self._coerce_track_id(track_id, kwargs)
            return self._load_one(audio_data, **kwargs)

        self.error_occurred.emit("load_audio: nothing to load")
        return None

    def load_clips(self, clips: Iterable[Any], **kwargs):
        """Load many clips. Each clip's start/trim is respected."""
        return [self.load_audio(c, **kwargs) for c in (clips or [])]

    def _require_transport_stopped(self):
        """Reject graph rebuilds while play/pause is active (mid-callback unsafe)."""
        if self.is_playing or self.is_paused:
            raise RuntimeError("stop transport before graph rebuild")

    @staticmethod
    def _dest_matches(dest, target) -> bool:
        """True if a stored output/send dest refers to ``target`` (track id or bus)."""
        if dest is None or isinstance(dest, bool):
            return False
        if isinstance(target, str):
            return isinstance(dest, str) and dest.strip() == target
        try:
            tid = int(target)
        except (TypeError, ValueError):
            return False
        if isinstance(dest, bool):
            return False
        if isinstance(dest, (int, np.integer)):
            return int(dest) == tid
        if isinstance(dest, str):
            stripped = dest.strip()
            if stripped.lstrip("-").isdigit():
                return int(stripped) == tid
        return False

    def _drop_sends_to_dest(self, dest_target):
        """Drop every track/bus send whose dest matches ``dest_target``."""
        for store, levels_map, modes_map in (
            (self.track_sends, self.track_send_levels, self.track_send_modes),
            (self.bus_sends, self.bus_send_levels, self.bus_send_modes),
        ):
            for src, dests in list(store.items()):
                kept = []
                for d in list(dests or []):
                    if self._dest_matches(d, dest_target):
                        levels = levels_map.get(src)
                        if levels is not None:
                            levels.pop(d, None)
                            if not levels:
                                levels_map.pop(src, None)
                        modes = modes_map.get(src)
                        if modes is not None:
                            modes.pop(d, None)
                            if not modes:
                                modes_map.pop(src, None)
                    else:
                        kept.append(d)
                if kept:
                    store[src] = kept
                else:
                    store.pop(src, None)

    def _reroute_outputs_away_from(self, dest_target):
        """Point track/bus main outputs that targeted ``dest_target`` to master."""
        for src, dest in list(self.track_outputs.items()):
            if self._dest_matches(dest, dest_target):
                self.track_outputs[src] = "master"
        for bus, dest in list(self.bus_outputs.items()):
            if self._dest_matches(dest, dest_target):
                self.bus_outputs.pop(bus, None)

    def unload_track(self, track_id: int):
        """Unload a track and clean all live-graph refs to it.

        Requires transport stopped. Other tracks/buses that output or send
        to this track are cleaned (outputs → master; sends dropped). The
        track's own outputs/sends/inserts and test-insert hooks are cleared
        so ``validate_graph`` stays clean — no stale refs left behind.
        """
        self._require_transport_stopped()
        track_id = self._coerce_track_id(track_id, {})
        # Clean inbound refs while the id is still meaningful.
        self._reroute_outputs_away_from(track_id)
        self._drop_sends_to_dest(track_id)
        self.clips = [c for c in self.clips if c.get("track_id") != track_id]
        if track_id in self.track_buffers:
            del self.track_buffers[track_id]
        if track_id in self.track_volumes:
            del self.track_volumes[track_id]
        if track_id in self.track_pans:
            del self.track_pans[track_id]
        if track_id in self.track_mutes:
            del self.track_mutes[track_id]
        if track_id in self.track_solos:
            del self.track_solos[track_id]
        if track_id in self.track_outputs:
            del self.track_outputs[track_id]
        self.track_sends.pop(track_id, None)
        self.track_send_levels.pop(track_id, None)
        self.track_send_modes.pop(track_id, None)
        self.channel_inserts.pop(track_id, None)
        try:
            _effects_clear_test_insert(track_id)
        except Exception:
            pass
        self._rebuild_track_buffers()

    def clear(self):
        """Remove all loaded clips and track buffers."""
        self._require_transport_stopped()
        self.clips = []
        self.track_buffers = {}
        self.master_mix = None
        self._clip_seq = 0
        self.track_outputs = {}
        self._buses = set()
        self.track_sends = {}
        self.track_send_levels = {}
        self.track_send_modes = {}
        self.channel_inserts = {}
        self.bus_volumes = {}
        self.bus_pans = {}
        self.bus_outputs = {}
        self.bus_sends = {}
        self.bus_send_levels = {}
        self.bus_send_modes = {}
        self._reset_meters()

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def play(self, start_position: float = 0.0):
        """Start playback of the current mix (device or offline)."""
        with self._play_lock:
            if self.is_playing and not self.is_paused:
                return

            self.start_position = float(start_position or 0.0)
            self.current_position = self.start_position
            self._stop_event.clear()

            # Render so tests / inspector can inspect master_mix and so
            # the callback has a consistent picture of clip placement.
            try:
                self.master_mix = self.render()
            except Exception as e:
                self.error_occurred.emit(f"Mix error: {e}")
                self.master_mix = np.zeros((0, self.channels), dtype=np.float32)

            started_device = False
            if self.has_audio_device():
                try:
                    self.stream = sd.OutputStream(
                        samplerate=self.sample_rate,
                        channels=self.channels,
                        blocksize=self.buffer_size,
                        callback=self._audio_callback,
                        dtype=np.float32,
                    )
                    self.stream.start()
                    started_device = True
                    self._offline_mode = False
                except Exception as e:
                    self.stream = None
                    self._offline_mode = True
                    print(f"Device playback failed, using offline path: {e}")

            self.is_playing = True
            self.is_paused = False
            try:
                self.update_timer.start()
            except Exception:
                pass

            if not started_device:
                self._offline_mode = True
                self._start_offline_playback()

            self.playback_started.emit()

    def pause(self):
        """Pause playback."""
        with self._play_lock:
            if not self.is_playing or self.is_paused:
                return

            self.is_paused = True
            try:
                self.update_timer.stop()
            except Exception:
                pass

            if self.stream:
                try:
                    self.stream.stop()
                except Exception:
                    pass

            self.playback_paused.emit()

    def stop(self):
        """Stop playback and reset position to 0."""
        with self._play_lock:
            was_playing = self.is_playing or self.is_paused
            self._stop_event.set()
            self.is_playing = False
            self.is_paused = False
            self.current_position = 0.0
            try:
                self.update_timer.stop()
            except Exception:
                pass

            if self.stream:
                try:
                    self.stream.stop()
                except Exception:
                    pass
                try:
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None

            offline = self._offline_thread
            self._offline_thread = None

        if offline is not None and offline.is_alive():
            if threading.current_thread() is not offline:
                offline.join(timeout=1.0)

        if was_playing:
            self.playback_stopped.emit()

    def seek(self, position: float):
        """Seek to position in seconds."""
        self.current_position = max(0.0, float(position))
        self.playback_position_changed.emit(self.current_position)

    # ------------------------------------------------------------------
    # Mixing / render (honors clip start + trim)
    # ------------------------------------------------------------------

    def mix(self, clips=None, start_time: float = 0.0, end_time: Optional[float] = None):
        """Mix clips (or currently loaded clips) honoring start/trim.

        Returns stereo float32. Clips whose ``start``/``start_time`` is
        > 0 begin at that timeline offset — they do **not** start at
        sample 0.
        """
        if clips is not None:
            records = []
            for clip in clips:
                rec = self._clip_to_record(clip, default_track=0)
                if rec is not None:
                    records.append(rec)
            mixed = self._mix_records(records, start_time=start_time, end_time=end_time)
        else:
            mixed = self.render(start_time=start_time, end_time=end_time)
        self.master_mix = mixed
        return mixed

    def mix_clips(self, clips=None, **kwargs):
        """Alias of mix() for clip lists."""
        return self.mix(clips=clips, **kwargs)

    def render(self, start_time: float = 0.0, end_time: Optional[float] = None):
        """Render the current session (loaded clips / track buffers)."""
        records = list(self.clips)
        if not records and self.track_buffers:
            for tid, buf in self.track_buffers.items():
                records.append({
                    "id": f"track-{tid}",
                    "track_id": tid,
                    "audio": ensure_stereo(buf),
                    "start": 0.0,
                    "start_sample": 0,
                    "trim_start": 0.0,
                    "trim_end": 0.0,
                    "length": None,
                    "path": None,
                })
        mixed = self._mix_records(records, start_time=start_time, end_time=end_time)
        self.master_mix = mixed
        return mixed

    def get_mix(self) -> np.ndarray:
        """Return last mix, rendering if needed."""
        if self.master_mix is None:
            return self.render()
        return self.master_mix

    def get_duration(self) -> float:
        """Timeline duration of the current mix in seconds."""
        end_sample = self._mix_end_sample(self.clips, self.track_buffers)
        return end_sample / float(self.sample_rate) if end_sample else 0.0

    # ------------------------------------------------------------------
    # Internal load / mix helpers
    # ------------------------------------------------------------------

    def _looks_like_path(self, value) -> bool:
        if isinstance(value, Path):
            return True
        if isinstance(value, str):
            lower = value.lower()
            if any(lower.endswith(ext) for ext in (
                ".wav", ".wave", ".flac", ".ogg", ".aiff", ".aif",
                ".mp3", ".m4a", ".au",
            )):
                return True
            if os.path.sep in value or (len(value) > 1 and value[1] == ":"):
                return True
            if os.path.exists(value):
                return True
        return False

    def _looks_like_clip(self, value) -> bool:
        if value is None or isinstance(value, (int, float, np.ndarray, str, Path)):
            return False
        if isinstance(value, dict):
            return True
        for key in (
            "start_time", "start", "trim_start", "trim", "file_path",
            "path", "audio_data", "audio", "offset", "length",
        ):
            if hasattr(value, key):
                return True
        return False

    def _coerce_track_id(self, track_id, kwargs) -> int:
        if track_id is None:
            track_id = kwargs.get("track_id", kwargs.get("track", 0))
        try:
            return int(track_id)
        except (TypeError, ValueError):
            return 0

    def _ensure_track_defaults(self, track_id: int):
        if track_id not in self.track_volumes:
            self.track_volumes[track_id] = 1.0
        if track_id not in self.track_pans:
            self.track_pans[track_id] = 0.0
        if track_id not in self.track_mutes:
            self.track_mutes[track_id] = False
        if track_id not in self.track_solos:
            self.track_solos[track_id] = False
        if track_id not in self.track_outputs:
            self.track_outputs[track_id] = "master"

    def _load_one(self, source, **kwargs):
        rec = self._clip_to_record(source, default_track=kwargs.get("track_id", 0), extra=kwargs)
        if rec is None:
            self.error_occurred.emit("load_audio: failed to decode source")
            return None
        self.clips.append(rec)
        self._ensure_track_defaults(rec["track_id"])
        self._rebuild_track_buffers()
        return rec

    def _clip_to_record(self, source, default_track=0, extra=None) -> Optional[Dict[str, Any]]:
        extra = extra or {}

        # Raw ndarray
        if isinstance(source, np.ndarray):
            audio = ensure_stereo(source)
            sr = int(extra.get("sample_rate") or extra.get("sr") or self.sample_rate)
            path = extra.get("path") or extra.get("file_path")
            start = _as_float(extra.get("start", extra.get("start_time", extra.get("offset", 0.0))))
            trim_start, trim_end, length = self._extra_trim(extra)
            start_sample_override = extra.get("start_sample", extra.get("start_samples"))
            audio = resample_audio(audio, sr, self.sample_rate)
            audio = apply_trim(audio, self.sample_rate, trim_start, trim_end, length)
            track_id = self._coerce_track_id(extra.get("track_id", default_track), extra)
            return self._make_record(
                audio, track_id, start, trim_start, trim_end, length,
                path, start_sample_override,
            )

        # Filesystem path
        if self._looks_like_path(source) and not isinstance(source, dict):
            try:
                audio, sr = read_wav(source)
            except Exception as e:
                self.error_occurred.emit(f"Failed to load WAV: {e}")
                return None
            audio = resample_audio(audio, sr, self.sample_rate)
            start = _as_float(extra.get("start", extra.get("start_time", extra.get("offset", 0.0))))
            trim_start, trim_end, length = self._extra_trim(extra)
            audio = apply_trim(audio, self.sample_rate, trim_start, trim_end, length)
            track_id = self._coerce_track_id(extra.get("track_id", default_track), extra)
            start_sample_override = extra.get("start_sample", extra.get("start_samples"))
            return self._make_record(
                audio, track_id, start, trim_start, trim_end, length,
                os.fspath(source), start_sample_override,
            )

        # Clip-like mapping / object
        path = _first_attr(source, _PATH_KEYS, extra.get("path") or extra.get("file_path"))
        audio = _first_attr(source, _AUDIO_KEYS, extra.get("audio_data") or extra.get("audio"))
        sr = _first_attr(source, _SR_KEYS, extra.get("sample_rate") or self.sample_rate)
        track_id = _first_attr(source, _TRACK_KEYS, extra.get("track_id", default_track))
        start = _first_attr(source, _START_KEYS, extra.get("start", extra.get("start_time", extra.get("offset", 0.0))))
        start = _as_float(start, 0.0)
        start_sample_override = _first_attr(
            source, _START_SAMPLE_KEYS,
            extra.get("start_sample", extra.get("start_samples")),
        )

        trim_field = _first_attr(source, ("trim",), extra.get("trim"))
        if isinstance(trim_field, (tuple, list)) and len(trim_field) >= 2:
            trim_start = _as_float(trim_field[0], 0.0)
            trim_end = _as_float(trim_field[1], 0.0)
        else:
            trim_start = _as_float(
                extra.get("trim_start",
                          _first_attr(source, _TRIM_START_KEYS, extra.get("trim", 0.0))),
                0.0,
            )
            trim_end = _as_float(
                extra.get("trim_end", _first_attr(source, _TRIM_END_KEYS, 0.0)),
                0.0,
            )

        length = extra.get("length", extra.get("duration"))
        if length is None:
            # Prefer explicit length/duration only when it looks like a
            # placed duration, not the full untrimmed file duration.
            length = _first_attr(source, ("length", "trim_length", "clip_length"))
        length = _as_optional_float(length)

        if audio is None and path:
            try:
                audio, file_sr = read_wav(path)
                sr = file_sr
            except Exception as e:
                self.error_occurred.emit(f"Failed to load WAV: {e}")
                return None

        if audio is None:
            return None

        audio = ensure_stereo(audio)
        audio = resample_audio(audio, int(sr or self.sample_rate), self.sample_rate)
        audio = apply_trim(audio, self.sample_rate, trim_start, trim_end, length)
        return self._make_record(
            audio,
            self._coerce_track_id(track_id, extra),
            start,
            trim_start,
            trim_end,
            length,
            os.fspath(path) if path else None,
            start_sample_override,
            clip_id=_first_attr(source, _ID_KEYS),
        )

    def _extra_trim(self, extra):
        trim_field = extra.get("trim")
        if isinstance(trim_field, (tuple, list)) and len(trim_field) >= 2:
            trim_start = _as_float(trim_field[0], 0.0)
            trim_end = _as_float(trim_field[1], 0.0)
        else:
            trim_start = _as_float(extra.get("trim_start", extra.get("trim", 0.0)), 0.0)
            trim_end = _as_float(extra.get("trim_end", 0.0), 0.0)
        length = _as_optional_float(extra.get("length", extra.get("duration")))
        return trim_start, trim_end, length

    def _make_record(
        self, audio, track_id, start, trim_start, trim_end, length,
        path, start_sample_override, clip_id=None,
    ):
        self._clip_seq += 1
        if start_sample_override is not None:
            try:
                start_sample = int(start_sample_override)
                start = start_sample / float(self.sample_rate)
            except (TypeError, ValueError):
                start_sample = int(round(_as_float(start, 0.0) * self.sample_rate))
        else:
            start_sample = int(round(_as_float(start, 0.0) * self.sample_rate))
        start_sample = max(0, start_sample)
        return {
            "id": clip_id or f"clip-{self._clip_seq}",
            "track_id": int(track_id) if track_id is not None else 0,
            "audio": ensure_stereo(audio),
            "start": float(start_sample) / float(self.sample_rate),
            "start_sample": start_sample,
            "trim_start": _as_float(trim_start, 0.0),
            "trim_end": _as_float(trim_end, 0.0),
            "length": length,
            "path": path,
        }

    def _rebuild_track_buffers(self):
        """Bake clips onto per-track buffers with start padding.

        Old mixers that read track_buffers[t][timeline_sample:] then
        honor start instead of treating every clip as beginning at 0.
        """
        by_track: Dict[int, List[Dict[str, Any]]] = {}
        for rec in self.clips:
            by_track.setdefault(rec["track_id"], []).append(rec)

        new_buffers = {}
        for tid, recs in by_track.items():
            end = 0
            for rec in recs:
                end = max(end, rec["start_sample"] + len(rec["audio"]))
            buf = np.zeros((end, self.channels), dtype=np.float32)
            for rec in recs:
                audio = rec["audio"]
                s = rec["start_sample"]
                n = len(audio)
                if n <= 0:
                    continue
                buf[s:s + n] += audio
            new_buffers[tid] = buf
            self._ensure_track_defaults(tid)
        self.track_buffers = new_buffers

    def _mix_end_sample(self, records, track_buffers=None) -> int:
        end = 0
        for rec in records or []:
            audio = rec.get("audio")
            if audio is None:
                continue
            end = max(end, int(rec.get("start_sample", 0)) + len(audio))
        if not records and track_buffers:
            for buf in track_buffers.values():
                end = max(end, len(buf))
        return end

    def _track_audible(self, track_id, any_solo: bool) -> bool:
        muted = self.track_mutes.get(track_id, False)
        soloed = self.track_solos.get(track_id, False)
        if muted and not (any_solo and soloed):
            return False
        if any_solo and not soloed:
            return False
        return True

    def _apply_track_fader(self, track_id, buf, any_solo):
        """Mute/solo/volume/pan the buffer. None if the track is inaudible."""
        if not self._track_audible(track_id, any_solo):
            return None
        segment = buf
        volume = self.track_volumes.get(track_id, 1.0)
        if volume != 1.0:
            segment = segment * volume
        pan = self.track_pans.get(track_id, 0.0)
        if pan != 0.0:
            segment = apply_pan(segment, pan)
        return segment

    def _apply_inserts(self, channel_id, audio):
        """On-channel ordered insert chain, then M1 test hooks.

        Canonical order: clips summed on the channel → insert chain →
        mute/solo/volume/pan → split to main output AND sends.
        Empty ``[]`` is dry. Inserts also run on named buses after the
        bus input is summed (see ``_mix_region``).

        Tests may assign ``engine._insert_processor`` (callable
        ``(track_id, audio) -> audio``) or use ``effects_rack.set_test_insert``.
        Those hooks run *after* the persisted chain so M1 tests stay valid.
        """
        if audio is None:
            return audio
        slots = self.get_inserts(channel_id)
        audio = _effects_apply_insert_chain(audio, slots)
        proc = self._insert_processor
        if callable(proc):
            out = proc(channel_id, audio)
            return audio if out is None else out
        return _effects_apply_inserts(channel_id, audio)

    def _reset_meters(self):
        self._meters = {
            "tracks": {},
            "buses": {},
            "master": {"peak": 0.0, "rms": 0.0},
        }

    def _meter_stats(self, buf):
        if buf is None:
            return {"peak": 0.0, "rms": 0.0}
        arr = np.asarray(buf)
        if arr.size == 0:
            return {"peak": 0.0, "rms": 0.0}
        peak = float(np.max(np.abs(arr)))
        rms = float(np.sqrt(np.mean(np.square(arr, dtype=np.float64))))
        if not math.isfinite(peak):
            peak = 0.0
        if not math.isfinite(rms):
            rms = 0.0
        return {"peak": peak, "rms": rms}

    def _record_meter(self, kind, key, buf):
        stats = self._meter_stats(buf)
        if kind == "master":
            self._meters["master"] = stats
        elif kind == "buses":
            self._meters["buses"][key] = stats
        else:
            self._meters["tracks"][int(key)] = stats

    def _mix_records(
        self,
        records: List[Dict[str, Any]],
        start_time: float = 0.0,
        end_time: Optional[float] = None,
    ) -> np.ndarray:
        sr = self.sample_rate
        start_sample = int(round(max(0.0, float(start_time or 0.0)) * sr))
        natural_end = self._mix_end_sample(records, None if records else self.track_buffers)
        if end_time is None:
            end_sample = natural_end
        else:
            end_sample = int(round(max(0.0, float(end_time)) * sr))
        end_sample = max(end_sample, start_sample)
        n_frames = end_sample - start_sample
        if n_frames <= 0:
            return np.zeros((0, self.channels), dtype=np.float32)
        return self._mix_region(start_sample, n_frames, records=records)

    def _iter_sources(self, records=None):
        if records:
            for rec in records:
                audio = rec.get("audio")
                if audio is None or len(audio) == 0:
                    continue
                yield rec.get("track_id", 0), ensure_stereo(audio), int(rec.get("start_sample", 0))
            return
        if self.clips:
            for rec in self.clips:
                audio = rec.get("audio")
                if audio is None or len(audio) == 0:
                    continue
                yield rec.get("track_id", 0), ensure_stereo(audio), int(rec.get("start_sample", 0))
            return
        for tid, buf in self.track_buffers.items():
            yield tid, ensure_stereo(buf), 0

    def _mix_region(self, start_sample: int, n_frames: int, records=None) -> np.ndarray:
        """Mix ``n_frames`` beginning at timeline ``start_sample``.

        Each source is placed at its own start_sample — this is the
        fix for mixes that previously ignored start and began at 0.

        Canonical on-channel mix order (one coherent path):
          1. clips summed on the track (this pass)
          2. on-channel insert chain (empty ``[]`` is dry)
          3. mute/solo/volume/pan
          4. split to main output (set_track_output) AND extra sends

        Send tap rule (documented):
          - ``post`` (default, M1): after mute/solo/volume/pan. Source
            volume 0 silences a post send.
          - ``pre``: after inserts, before volume/pan. Mute/solo still
            silence both taps. Pre send ignores source fader/pan.

        Track→track remains one-hop (source own-sum into dest before
        dest fader). Buses are real mixer channels: inserts, fader, pan,
        extra sends, then dest Master or another bus/track. Default bus
        (vol 1, pan 0, dest master, no inserts) matches M1 bus-as-sum.
        """
        self._reset_meters()
        mix = np.zeros((n_frames, self.channels), dtype=np.float32)
        any_solo = any(self.track_solos.values()) if self.track_solos else False
        region_end = start_sample + n_frames

        # Pass 1: each track's own clip sum (raw, no fader)
        own: Dict[int, np.ndarray] = {}

        def _buf(tid: int) -> np.ndarray:
            tid = int(tid)
            if tid not in own:
                own[tid] = np.zeros((n_frames, self.channels), dtype=np.float32)
            return own[tid]

        for track_id, audio, src_start in self._iter_sources(records):
            track_id = int(track_id) if track_id is not None else 0
            buf = _buf(track_id)
            src_end = src_start + len(audio)
            ov_start = max(start_sample, src_start)
            ov_end = min(region_end, src_end)
            if ov_start >= ov_end:
                continue
            dest_off = ov_start - start_sample
            src_off = ov_start - src_start
            n = ov_end - ov_start
            buf[dest_off:dest_off + n] += audio[src_off:src_off + n]

        # Pass 1b: on-channel insert chain. Before fader/split.
        for tid in list(own.keys()):
            processed = self._apply_inserts(tid, own[tid])
            if processed is not None:
                own[tid] = processed

        # Pass 2: route source own-sum into dest track before dest fader.
        # Snapshot own clips so A→B only adds A's clips (one hop, no walker).
        combined = {tid: arr.copy() for tid, arr in own.items()}
        for src_tid, buf in own.items():
            dest = self.get_track_output(src_tid)
            if dest == "master":
                continue
            if isinstance(dest, bool) or not isinstance(dest, (int, np.integer)):
                continue
            dest_id = int(dest)
            if dest_id not in combined:
                combined[dest_id] = np.zeros((n_frames, self.channels), dtype=np.float32)
                self._ensure_track_defaults(dest_id)
            combined[dest_id] += buf

        known_buses = set(self._buses)
        bus_inputs: Dict[str, np.ndarray] = {}

        def _ensure_bus_input(name: str) -> np.ndarray:
            if name not in bus_inputs:
                bus_inputs[name] = np.zeros((n_frames, self.channels), dtype=np.float32)
            return bus_inputs[name]

        def _scale_send(segment, level):
            if level == 1.0:
                return segment
            return segment * np.float32(level)

        post_fader_own = {}
        pre_fader_own = {}

        def _own_pre_fader(tid):
            if tid not in pre_fader_own:
                src_buf = own.get(tid)
                if src_buf is None or not self._track_audible(tid, any_solo):
                    pre_fader_own[tid] = None
                else:
                    pre_fader_own[tid] = src_buf
            return pre_fader_own[tid]

        def _own_post_fader(tid):
            if tid not in post_fader_own:
                src_buf = own.get(tid)
                if src_buf is None:
                    post_fader_own[tid] = None
                else:
                    post_fader_own[tid] = self._apply_track_fader(
                        tid, src_buf, any_solo
                    )
            return post_fader_own[tid]

        def _route_send_audio(dest, send_buf):
            if isinstance(dest, bool):
                return
            if isinstance(dest, (int, np.integer)):
                dest_id = int(dest)
                if dest_id not in combined:
                    combined[dest_id] = np.zeros(
                        (n_frames, self.channels), dtype=np.float32
                    )
                    self._ensure_track_defaults(dest_id)
                combined[dest_id] += send_buf
            elif isinstance(dest, str) and dest in known_buses:
                _ensure_bus_input(dest)
                bus_inputs[dest] += send_buf

        for src_key, dests in self.track_sends.items():
            try:
                if isinstance(src_key, bool):
                    continue
                src_tid = int(src_key)
            except (TypeError, ValueError):
                continue
            src_levels = self.track_send_levels.get(src_tid) or {}
            src_modes = self.track_send_modes.get(src_tid) or {}
            for dest in dests or []:
                if isinstance(dest, bool):
                    continue
                level = src_levels.get(dest, 1.0)
                try:
                    level = float(level)
                except (TypeError, ValueError):
                    level = 1.0
                if not math.isfinite(level) or level <= 0.0:
                    continue
                mode = src_modes.get(dest, "post")
                if mode == "pre":
                    segment = _own_pre_fader(src_tid)
                else:
                    segment = _own_post_fader(src_tid)
                if segment is None:
                    continue
                _route_send_audio(dest, _scale_send(segment, level))

        # Pass 3/4: channel out. dest=master → mix; dest=bus → bus input.
        for track_id, buf in combined.items():
            segment = self._apply_track_fader(track_id, buf, any_solo)
            self._record_meter("tracks", track_id, segment)
            dest = self.get_track_output(track_id)
            if segment is None:
                continue
            if dest == "master":
                mix += segment
            elif isinstance(dest, str) and dest in known_buses:
                _ensure_bus_input(dest)
                bus_inputs[dest] += segment

        def _apply_bus_fader(name, buf):
            volume = self.bus_volumes.get(name, 1.0)
            segment = buf if volume == 1.0 else buf * np.float32(volume)
            pan = self.bus_pans.get(name, 0.0)
            if pan != 0.0:
                segment = apply_pan(segment, pan)
            return segment

        def _spill_into_track(dest_id, buf):
            """Bus → track: dest fader, then that track's dest (master/bus)."""
            segment = self._apply_track_fader(dest_id, buf, any_solo)
            if segment is None:
                return
            dest = self.get_track_output(dest_id)
            if dest == "master":
                mix[...] += segment
            elif isinstance(dest, str) and dest in known_buses:
                _ensure_bus_input(dest)
                bus_inputs[dest] += segment

        for bus in self._bus_process_order():
            buf = bus_inputs.get(bus)
            if buf is None:
                buf = np.zeros((n_frames, self.channels), dtype=np.float32)
            processed = self._apply_inserts(bus, buf)
            if processed is not None:
                buf = processed
            pre = buf
            post = _apply_bus_fader(bus, pre)
            self._record_meter("buses", bus, post)

            src_levels = self.bus_send_levels.get(bus) or {}
            src_modes = self.bus_send_modes.get(bus) or {}
            for dest in self.bus_sends.get(bus) or []:
                if isinstance(dest, bool):
                    continue
                level = src_levels.get(dest, 1.0)
                try:
                    level = float(level)
                except (TypeError, ValueError):
                    level = 1.0
                if not math.isfinite(level) or level <= 0.0:
                    continue
                mode = src_modes.get(dest, "post")
                segment = pre if mode == "pre" else post
                send_buf = _scale_send(segment, level)
                if isinstance(dest, str) and dest in known_buses:
                    _ensure_bus_input(dest)
                    bus_inputs[dest] += send_buf
                elif isinstance(dest, (int, np.integer)):
                    _spill_into_track(int(dest), send_buf)

            dest = self.get_bus_output(bus)
            if dest == "master":
                mix += post
            elif isinstance(dest, str) and dest in known_buses:
                _ensure_bus_input(dest)
                bus_inputs[dest] += post
            elif isinstance(dest, (int, np.integer)):
                _spill_into_track(int(dest), post)

        mix = np.tanh(mix)
        self._record_meter("master", "master", mix)
        return mix.astype(np.float32, copy=False)

    # ------------------------------------------------------------------
    # Device / offline callback
    # ------------------------------------------------------------------

    def _audio_callback(self, outdata, frames, time_info, status):
        """sounddevice callback — mixes honoring clip start/trim."""
        if status:
            print(f"Audio callback status: {status}")

        if self.is_paused or not self.is_playing:
            outdata[:] = 0
            return

        start_sample = int(self.current_position * self.sample_rate)
        mix = self._mix_region(start_sample, frames)
        outdata[:] = mix

        self.current_position += frames / float(self.sample_rate)

        max_length = self._mix_end_sample(self.clips, self.track_buffers)
        if start_sample >= max_length:
            # Flag finish; avoid joining ourselves from the audio thread
            threading.Thread(target=self._finish_playback, daemon=True).start()

    def _finish_playback(self):
        self.stop()
        self.playback_finished.emit()

    def _start_offline_playback(self):
        if self._offline_thread is not None and self._offline_thread.is_alive():
            return

        def _run():
            chunk = max(1, int(self.buffer_size))
            sr = float(self.sample_rate)
            interval = chunk / sr
            while not self._stop_event.is_set():
                if not self.is_playing:
                    break
                if self.is_paused:
                    time.sleep(0.02)
                    continue
                start_sample = int(self.current_position * self.sample_rate)
                max_length = self._mix_end_sample(self.clips, self.track_buffers)
                if max_length and start_sample >= max_length:
                    self._finish_playback()
                    break
                # Advance as if the device consumed a block. The mix
                # itself is already in master_mix / render() for tests.
                time.sleep(interval)
                if self._stop_event.is_set():
                    break
                self.current_position += interval

        self._offline_thread = threading.Thread(target=_run, name="aria-offline-play", daemon=True)
        self._offline_thread.start()

    def _update_position(self):
        """Update position for UI."""
        self.playback_position_changed.emit(self.current_position)

    # ------------------------------------------------------------------
    # Track controls
    # ------------------------------------------------------------------

    def set_track_volume(self, track_id: int, volume: float):
        """Set track volume (0.0 to 1.0)"""
        self.track_volumes[track_id] = max(0.0, min(1.0, volume))

    def set_track_pan(self, track_id: int, pan: float):
        """Set track pan (-1.0 to 1.0)"""
        self.track_pans[track_id] = max(-1.0, min(1.0, pan))

    def set_track_mute(self, track_id: int, muted: bool):
        """Set track mute state"""
        self.track_mutes[track_id] = muted

    def set_track_solo(self, track_id: int, soloed: bool):
        """Set track solo state"""
        self.track_solos[track_id] = soloed

    def _follow_dest_node(self, dest):
        """Next graph node for a dest, or None at master / unknown terminal."""
        if dest is None or dest == "":
            return None
        if isinstance(dest, bool):
            return None
        if isinstance(dest, (int, np.integer)):
            return ("t", int(dest))
        if isinstance(dest, str):
            stripped = dest.strip()
            if not stripped or stripped.lower() == "master":
                return None
            if stripped.lstrip("-").isdigit():
                return ("t", int(stripped))
            if stripped in self._buses:
                return ("b", stripped)
            return None
        return None

    def _node_output(self, node):
        kind, ident = node
        if kind == "t":
            return self.get_track_output(ident)
        return self.get_bus_output(ident)

    def _would_create_node_cycle(self, src_node, dest) -> bool:
        """True if src_node → dest closes a main-output cycle."""
        current = self._follow_dest_node(dest)
        if current is None:
            return False
        if current == src_node:
            return True
        seen = set()
        while current is not None:
            if current == src_node or current in seen:
                return True
            seen.add(current)
            current = self._follow_dest_node(self._node_output(current))
        return False

    def _would_create_output_cycle(self, track_id: int, dest_id: int) -> bool:
        """True if routing track_id → dest_id would close a cycle.

        Walk dest_id's existing output chain (tracks and buses). If we
        reach track_id, the new edge would loop. ``"master"`` / missing
        dest ends the walk. Mix stays one-hop for tracks; this is setter-only.
        """
        return self._would_create_node_cycle(("t", int(track_id)), dest_id)

    def set_track_output(self, track_id: int, dest):
        """Set where a track's audio is summed.

        dest ``None`` / missing / ``"master"`` → today's mix (track sums
        into master after its own volume/pan/mute/solo). dest an int
        track id → that track's buffer (then dest fader applies). dest a
        known bus name → that bus (source fader/mute/solo apply, then the
        bus channel: inserts/fader/pan/dest). Unknown dest is rejected.
        Self-output and multi-track/bus cycles (0→1→0, 0→drum→0, …) are
        rejected in this setter so the mix stays well-defined without a
        recursive track walker.
        """
        track_id = self._coerce_track_id(track_id, {})
        if dest is None:
            self._ensure_track_defaults(track_id)
            self.track_outputs[track_id] = "master"
            return
        if isinstance(dest, str):
            stripped = dest.strip()
            if stripped == "" or stripped.lower() == "master":
                self._ensure_track_defaults(track_id)
                self.track_outputs[track_id] = "master"
                return
            if stripped.lstrip("-").isdigit():
                dest_id = int(stripped)
            elif stripped in self._buses:
                if self._would_create_node_cycle(("t", track_id), stripped):
                    raise ValueError(
                        f"Track output cycle: routing {track_id} to {stripped!r} "
                        f"would create a cycle"
                    )
                self._ensure_track_defaults(track_id)
                self.track_outputs[track_id] = stripped
                return
            else:
                raise ValueError(f"Unknown track output dest: {dest!r}")
        elif isinstance(dest, bool) or dest is True or dest is False:
            raise ValueError(f"Unknown track output dest: {dest!r}")
        elif isinstance(dest, (int, np.integer)):
            dest_id = int(dest)
        else:
            raise ValueError(f"Unknown track output dest: {dest!r}")

        if dest_id == track_id:
            raise ValueError(f"Track {track_id} cannot output to itself")

        if self._would_create_output_cycle(track_id, dest_id):
            raise ValueError(
                f"Track output cycle: routing {track_id} to {dest_id} would create a cycle"
            )

        self._ensure_track_defaults(track_id)
        self._ensure_track_defaults(dest_id)
        self.track_outputs[track_id] = dest_id

    def get_track_output(self, track_id: int):
        """Return ``"master"``, dest track id (int), or a bus name (str)."""
        try:
            track_id = int(track_id)
        except (TypeError, ValueError):
            track_id = 0
        dest = self.track_outputs.get(track_id)
        if dest is None:
            dest = self.track_outputs.get(str(track_id), "master")
        if dest is None or dest == "":
            return "master"
        if isinstance(dest, bool):
            return dest
        if isinstance(dest, str):
            stripped = dest.strip()
            if stripped.lower() == "master":
                return "master"
            if stripped.lstrip("-").isdigit():
                return int(stripped)
            return stripped
        if isinstance(dest, (int, np.integer)):
            return int(dest)
        return dest

    def add_bus(self, name: str):
        """Register a named mix bus (live graph; ProjectManager persists in .daw).

        Bus names are non-empty strings other than ``"master"``. Duplicate
        add is idempotent. Default channel: volume 1.0, pan 0.0, dest master.
        """
        if not isinstance(name, str):
            raise ValueError(f"Bus name must be a string, got {type(name).__name__}")
        name = name.strip()
        if not name:
            raise ValueError("Bus name must be non-empty")
        if name.lower() == "master":
            raise ValueError('Bus name cannot be "master"')
        self._buses.add(name)

    def list_buses(self):
        """Return known bus names (sorted)."""
        return sorted(self._buses)

    def get_buses(self):
        """Alias of list_buses()."""
        return self.list_buses()

    def remove_bus(self, name: str):
        """Remove a named bus and clean routing that pointed at it.

        Requires transport stopped. Track/bus outputs to this bus become
        ``"master"``; sends to this bus are dropped. Bus channel state
        (volume/pan/output/sends/inserts) is cleared. Missing bus is a
        no-op (idempotent). ``"master"`` / empty names are rejected.
        """
        self._require_transport_stopped()
        if not isinstance(name, str):
            raise ValueError(f"Bus name must be a string, got {type(name).__name__}")
        name = name.strip()
        if not name:
            raise ValueError("Bus name must be non-empty")
        if name.lower() == "master":
            raise ValueError('Bus name cannot be "master"')
        if name not in self._buses:
            return
        self._reroute_outputs_away_from(name)
        self._drop_sends_to_dest(name)
        self._buses.discard(name)
        self.bus_outputs.pop(name, None)
        self.bus_volumes.pop(name, None)
        self.bus_pans.pop(name, None)
        self.bus_sends.pop(name, None)
        self.bus_send_levels.pop(name, None)
        self.bus_send_modes.pop(name, None)
        self.channel_inserts.pop(name, None)
        try:
            _effects_clear_test_insert(name)
        except Exception:
            pass

    def rebuild_graph(self):
        """Re-validate the live graph after structural edits.

        Does not silently mutate routing — ``unload_track`` / ``remove_bus``
        are responsible for leaving a valid graph. Requires transport stopped.
        """
        self._require_transport_stopped()
        return self.validate_graph()

    def _require_bus(self, name):
        if not isinstance(name, str):
            raise ValueError(f"Unknown bus: {name!r}")
        name = name.strip()
        if name not in self._buses:
            raise ValueError(f"Unknown bus: {name!r}")
        return name

    def get_bus_output(self, name):
        """Return ``"master"``, dest track id, or another bus name."""
        if not isinstance(name, str):
            return "master"
        name = name.strip()
        dest = self.bus_outputs.get(name)
        if dest is None or dest == "":
            return "master"
        if isinstance(dest, bool):
            return dest
        if isinstance(dest, str):
            stripped = dest.strip()
            if stripped.lower() == "master":
                return "master"
            if stripped.lstrip("-").isdigit():
                return int(stripped)
            return stripped
        if isinstance(dest, (int, np.integer)):
            return int(dest)
        return dest

    def set_bus_output(self, name, dest):
        """Route a bus to Master (default), another bus, or a live track.

        Track dests must themselves output to master or a bus (M1 one-hop:
        we apply the dest track fader, then that track's dest — we do not
        walk track→track). Cycles and unknown dests are rejected.
        """
        name = self._require_bus(name)
        if dest is None:
            self.bus_outputs.pop(name, None)
            return
        if isinstance(dest, str):
            stripped = dest.strip()
            if stripped == "" or stripped.lower() == "master":
                self.bus_outputs.pop(name, None)
                return
            if stripped.lstrip("-").isdigit():
                dest_norm = int(stripped)
            elif stripped == name:
                raise ValueError(f"Bus {name!r} cannot output to itself")
            elif stripped in self._buses:
                dest_norm = stripped
            else:
                raise ValueError(f"Unknown bus output dest: {dest!r}")
        elif isinstance(dest, bool):
            raise ValueError(f"Unknown bus output dest: {dest!r}")
        elif isinstance(dest, (int, np.integer)):
            dest_norm = int(dest)
        else:
            raise ValueError(f"Unknown bus output dest: {dest!r}")

        if dest_norm == name:
            raise ValueError(f"Bus {name!r} cannot output to itself")
        if isinstance(dest_norm, int):
            if dest_norm not in self._live_track_ids():
                raise ValueError(f"Unknown bus output dest: {dest_norm}")
            track_dest = self.get_track_output(dest_norm)
            if isinstance(track_dest, (int, np.integer)):
                raise ValueError(
                    f"Bus {name!r} cannot output to track {dest_norm} because "
                    f"that track outputs to another track (M1 one-hop)"
                )
        if self._would_create_node_cycle(("b", name), dest_norm):
            raise ValueError(
                f"Bus output cycle: routing {name!r} to {dest_norm!r} would create a cycle"
            )
        self.bus_outputs[name] = dest_norm

    def set_bus_volume(self, name, volume: float):
        name = self._require_bus(name)
        self.bus_volumes[name] = max(0.0, min(1.0, float(volume)))

    def get_bus_volume(self, name) -> float:
        name = self._require_bus(name)
        return float(self.bus_volumes.get(name, 1.0))

    def set_bus_pan(self, name, pan: float):
        name = self._require_bus(name)
        self.bus_pans[name] = max(-1.0, min(1.0, float(pan)))

    def get_bus_pan(self, name) -> float:
        name = self._require_bus(name)
        return float(self.bus_pans.get(name, 0.0))

    def _bus_process_order(self):
        """Topological order of buses (main dest + bus-to-bus sends)."""
        buses = list(self._buses)
        incoming = {b: 0 for b in buses}
        edges = {b: [] for b in buses}
        for bus in buses:
            targets = []
            dest = self.get_bus_output(bus)
            if isinstance(dest, str) and dest in self._buses:
                targets.append(dest)
            elif isinstance(dest, (int, np.integer)):
                td = self.get_track_output(int(dest))
                if isinstance(td, str) and td in self._buses:
                    targets.append(td)
            for sdest in self.bus_sends.get(bus) or []:
                if isinstance(sdest, str) and sdest in self._buses:
                    targets.append(sdest)
            for target in targets:
                edges[bus].append(target)
                incoming[target] += 1
        queue = [b for b in sorted(buses) if incoming[b] == 0]
        order = []
        while queue:
            bus = queue.pop(0)
            order.append(bus)
            for target in edges[bus]:
                incoming[target] -= 1
                if incoming[target] == 0:
                    queue.append(target)
                    queue.sort()
        for bus in sorted(buses):
            if bus not in order:
                order.append(bus)
        return order

    def _insert_channel_key(self, channel_id, *, require_known=False):
        """Normalize a track id or bus name used as an insert channel."""
        if isinstance(channel_id, bool):
            raise ValueError(f"Unknown insert channel: {channel_id!r}")
        if isinstance(channel_id, str):
            stripped = channel_id.strip()
            if stripped in self._buses:
                return stripped
            if stripped.lstrip("-").isdigit():
                return int(stripped)
            if require_known:
                raise ValueError(f"Unknown insert channel: {channel_id!r}")
            return stripped
        try:
            return int(channel_id)
        except (TypeError, ValueError):
            raise ValueError(f"Unknown insert channel: {channel_id!r}")

    def _normalize_insert_slot(self, slot):
        if not isinstance(slot, dict):
            raise ValueError(f"Insert slot must be a dict, got {type(slot).__name__}")
        out = dict(slot)
        typ = str(out.get("type") or "identity").strip().lower()
        out["type"] = typ or "identity"
        if "enabled" in out:
            out["enabled"] = bool(out["enabled"])
        return out

    def set_inserts(self, channel_id, slots):
        """Replace the ordered insert chain on a track or bus.

        Empty list is dry/identity. Each slot is a dict (type, enabled,
        params). Unknown types are stored and treated as identity.
        """
        key = self._insert_channel_key(channel_id, require_known=True)
        if slots is None:
            slots = []
        if not isinstance(slots, list):
            raise ValueError("Inserts must be a list of slot dicts")
        self.channel_inserts[key] = [self._normalize_insert_slot(s) for s in slots]

    def get_inserts(self, channel_id):
        """Return a copy of the insert slot list (empty = dry)."""
        try:
            key = self._insert_channel_key(channel_id, require_known=False)
        except ValueError:
            return []
        return [dict(s) for s in self.channel_inserts.get(key, [])]

    def add_insert(self, channel_id, slot):
        """Append one slot to the channel's insert chain."""
        key = self._insert_channel_key(channel_id, require_known=True)
        chain = list(self.channel_inserts.get(key, []))
        chain.append(self._normalize_insert_slot(slot))
        self.channel_inserts[key] = chain

    def _validate_send_mode(self, mode):
        if mode is None:
            return "post"
        if not isinstance(mode, str):
            raise ValueError(f"Send mode must be 'pre' or 'post', got {mode!r}")
        stripped = mode.strip().lower()
        if stripped in ("pre", "pre-fader", "prefader"):
            return "pre"
        if stripped in ("post", "post-fader", "postfader", ""):
            return "post"
        raise ValueError(f"Send mode must be 'pre' or 'post', got {mode!r}")

    def get_meters(self):
        """Last-mix peak/rms for tracks, buses, and Master.

        Values are finite floats from the most recent ``mix`` / ``render``.
        Missing channels default to 0. No UI; engine data only.
        """
        return {
            "tracks": {int(k): dict(v) for k, v in self._meters.get("tracks", {}).items()},
            "buses": {str(k): dict(v) for k, v in self._meters.get("buses", {}).items()},
            "master": dict(self._meters.get("master") or {"peak": 0.0, "rms": 0.0}),
        }

    def get_meter(self, channel="master"):
        """Peak/rms for ``\"master\"``, a bus name, or a track id."""
        meters = self.get_meters()
        if channel is None or (
            isinstance(channel, str) and channel.strip().lower() == "master"
        ):
            return meters["master"]
        if isinstance(channel, str) and channel.strip() in self._buses:
            return meters["buses"].get(channel.strip(), {"peak": 0.0, "rms": 0.0})
        try:
            tid = int(channel)
        except (TypeError, ValueError):
            return {"peak": 0.0, "rms": 0.0}
        return meters["tracks"].get(tid, {"peak": 0.0, "rms": 0.0})

    def _is_bus_source(self, source) -> bool:
        return isinstance(source, str) and source.strip() in self._buses

    def _resolve_send_dest(self, source, dest):
        """Normalize a send dest or raise ValueError.

        dest is a known bus name or a live track id. ``"master"`` is
        rejected: the main output path already covers master, and a send
        to master would double the source. Self-send is rejected. Track
        dests must already be live (unlike ``set_track_output``, which
        may create dest tracks).
        """
        if dest is None:
            raise ValueError(f"Unknown send dest: {dest!r}")
        if isinstance(dest, str):
            stripped = dest.strip()
            if stripped == "" or stripped.lower() == "master":
                raise ValueError('Send dest cannot be "master"')
            if stripped.lstrip("-").isdigit():
                dest_id = int(stripped)
            elif stripped in self._buses:
                if isinstance(source, str) and source.strip() == stripped:
                    raise ValueError(f"Bus {stripped!r} cannot send to itself")
                return stripped
            else:
                raise ValueError(f"Unknown send dest: {dest!r}")
        elif isinstance(dest, bool):
            raise ValueError(f"Unknown send dest: {dest!r}")
        elif isinstance(dest, (int, np.integer)):
            dest_id = int(dest)
        else:
            raise ValueError(f"Unknown send dest: {dest!r}")

        if source == dest_id:
            raise ValueError(f"Track {source} cannot send to itself")
        if dest_id not in self._live_track_ids():
            raise ValueError(f"Unknown send dest: {dest_id}")
        return dest_id

    def _validate_send_level(self, level):
        """Finite non-negative gain. 0.0 is valid (silence only the send)."""
        if isinstance(level, (bool, np.bool_)):
            raise ValueError(
                f"Send level must be a finite non-negative number, got {level!r}"
            )
        try:
            g = float(level)
        except (TypeError, ValueError):
            raise ValueError(
                f"Send level must be a finite non-negative number, got {level!r}"
            )
        if not math.isfinite(g) or g < 0.0:
            raise ValueError(
                f"Send level must be a finite non-negative number, got {level!r}"
            )
        return g

    def add_send(self, track_id, dest, level=1.0, mode="post"):
        """Add an extra send from a track or bus to dest.

        A send is EXTRA: the source still follows its main output, and a
        copy is multiplied by ``level`` and mixed into ``dest``.
        ``mode`` is ``\"post\"`` (default, after fader — M1) or ``\"pre\"``
        (after inserts, before fader/pan). Mute/solo silence both taps.

        dest cannot be ``\"master\"``. Duplicate send to the same dest is
        idempotent (existing level/mode kept). Self-send is rejected.
        Track→track sends do not participate in main-output cycle
        detection (M1 extra-path rule). Bus→bus sends that would cycle
        the bus graph are rejected. Unknown dest is ValueError.
        """
        mode = self._validate_send_mode(mode)
        level = self._validate_send_level(level)
        if self._is_bus_source(track_id):
            source = track_id.strip()
            dest_norm = self._resolve_send_dest(source, dest)
            if isinstance(dest_norm, str) and dest_norm in self._buses:
                if self._would_create_node_cycle(("b", source), dest_norm):
                    raise ValueError(
                        f"Send cycle: {source!r} → {dest_norm!r} would create a cycle"
                    )
            sends = self.bus_sends.setdefault(source, [])
            if dest_norm not in sends:
                sends.append(dest_norm)
                self.bus_send_levels.setdefault(source, {})[dest_norm] = level
                self.bus_send_modes.setdefault(source, {})[dest_norm] = mode
            return dest_norm
        source = self._coerce_track_id(track_id, {})
        dest_norm = self._resolve_send_dest(source, dest)
        self._ensure_track_defaults(source)
        sends = self.track_sends.setdefault(source, [])
        if dest_norm not in sends:
            sends.append(dest_norm)
            self.track_send_levels.setdefault(source, {})[dest_norm] = level
            self.track_send_modes.setdefault(source, {})[dest_norm] = mode
        return dest_norm

    def get_sends(self, track_id):
        """Return a copy of extra send dests (bus names / track ids)."""
        if self._is_bus_source(track_id):
            return list(self.bus_sends.get(track_id.strip(), []))
        track_id = self._coerce_track_id(track_id, {})
        return list(self.track_sends.get(track_id, []))

    def set_send_level(self, track_id, dest, level):
        """Set per-send gain. dest must already be a send on this source."""
        level = self._validate_send_level(level)
        if self._is_bus_source(track_id):
            source = track_id.strip()
            dest_norm = self._resolve_send_dest(source, dest)
            sends = self.bus_sends.get(source) or []
            if dest_norm not in sends:
                raise ValueError(f"No send from bus {source!r} to {dest_norm!r}")
            self.bus_send_levels.setdefault(source, {})[dest_norm] = level
            return
        source = self._coerce_track_id(track_id, {})
        dest_norm = self._resolve_send_dest(source, dest)
        sends = self.track_sends.get(source) or []
        if dest_norm not in sends:
            raise ValueError(f"No send from track {source} to {dest_norm!r}")
        self.track_send_levels.setdefault(source, {})[dest_norm] = level

    def get_send_level(self, track_id, dest):
        """Return the per-send gain (1.0 if never set). dest must be a send."""
        if self._is_bus_source(track_id):
            source = track_id.strip()
            dest_norm = self._resolve_send_dest(source, dest)
            sends = self.bus_sends.get(source) or []
            if dest_norm not in sends:
                raise ValueError(f"No send from bus {source!r} to {dest_norm!r}")
            return float(self.bus_send_levels.get(source, {}).get(dest_norm, 1.0))
        source = self._coerce_track_id(track_id, {})
        dest_norm = self._resolve_send_dest(source, dest)
        sends = self.track_sends.get(source) or []
        if dest_norm not in sends:
            raise ValueError(f"No send from track {source} to {dest_norm!r}")
        return float(self.track_send_levels.get(source, {}).get(dest_norm, 1.0))

    def set_send_mode(self, track_id, dest, mode):
        """Set ``pre`` or ``post`` (default) for an existing send."""
        mode = self._validate_send_mode(mode)
        if self._is_bus_source(track_id):
            source = track_id.strip()
            dest_norm = self._resolve_send_dest(source, dest)
            sends = self.bus_sends.get(source) or []
            if dest_norm not in sends:
                raise ValueError(f"No send from bus {source!r} to {dest_norm!r}")
            self.bus_send_modes.setdefault(source, {})[dest_norm] = mode
            return mode
        source = self._coerce_track_id(track_id, {})
        dest_norm = self._resolve_send_dest(source, dest)
        sends = self.track_sends.get(source) or []
        if dest_norm not in sends:
            raise ValueError(f"No send from track {source} to {dest_norm!r}")
        self.track_send_modes.setdefault(source, {})[dest_norm] = mode
        return mode

    def get_send_mode(self, track_id, dest):
        """Return ``pre`` or ``post`` (default) for an existing send."""
        if self._is_bus_source(track_id):
            source = track_id.strip()
            dest_norm = self._resolve_send_dest(source, dest)
            sends = self.bus_sends.get(source) or []
            if dest_norm not in sends:
                raise ValueError(f"No send from bus {source!r} to {dest_norm!r}")
            return self.bus_send_modes.get(source, {}).get(dest_norm, "post")
        source = self._coerce_track_id(track_id, {})
        dest_norm = self._resolve_send_dest(source, dest)
        sends = self.track_sends.get(source) or []
        if dest_norm not in sends:
            raise ValueError(f"No send from track {source} to {dest_norm!r}")
        return self.track_send_modes.get(source, {}).get(dest_norm, "post")

    def remove_send(self, track_id, dest):
        """Remove one send if present. Unknown / missing dest is a no-op."""
        if self._is_bus_source(track_id):
            source = track_id.strip()
            sends = self.bus_sends.get(source)
            maps = (self.bus_send_levels, self.bus_send_modes)
            store = self.bus_sends
        else:
            source = self._coerce_track_id(track_id, {})
            sends = self.track_sends.get(source)
            maps = (self.track_send_levels, self.track_send_modes)
            store = self.track_sends
        if not sends:
            return
        try:
            dest_norm = self._resolve_send_dest(source, dest)
        except ValueError:
            dest_norm = dest.strip() if isinstance(dest, str) else dest
        if dest_norm in sends:
            sends.remove(dest_norm)
            for mapping in maps:
                levels = mapping.get(source)
                if levels is not None:
                    levels.pop(dest_norm, None)
                    if not levels:
                        mapping.pop(source, None)
        if not sends:
            store.pop(source, None)

    def _live_track_ids(self):
        """Tracks that have been loaded or have volume/pan/mute/solo state.

        Live = keys in ``track_buffers`` / clips, or tracks that have
        volume/pan/mute/solo state. Dest tracks created by
        ``set_track_output`` get those defaults, so they are live.
        A ``track_outputs`` entry alone does **not** make a track live,
        so leftover outputs after unload can be flagged as stale.
        """
        ids = set()
        for mapping in (
            self.track_buffers,
            self.track_volumes,
            self.track_pans,
            self.track_mutes,
            self.track_solos,
        ):
            for key in mapping:
                try:
                    if isinstance(key, bool):
                        continue
                    ids.add(int(key))
                except (TypeError, ValueError):
                    pass
        for rec in self.clips or []:
            tid = rec.get("track_id")
            if tid is None or isinstance(tid, bool):
                continue
            try:
                ids.add(int(tid))
            except (TypeError, ValueError):
                pass
        return ids

    def validate_graph(self):
        """Validate the current routing graph (read-only).

        Returns None if valid. Raises ValueError describing the problem(s).
        Does not mutate ``track_outputs`` or dests.

        Rejects:
        - dangling dest: dest track id that is not a live track, or dest
          bus name that was never added
        - type errors: dest not ``"master"``, an int track id, or a known
          bus name (list, float, None, bool, …)
        - stale ``track_outputs`` entries whose source track is no longer
          live (unloaded/cleared leftovers)
        - cycles already present in the stored graph (via
          ``_would_create_output_cycle``; not reimplemented here)

        Live tracks: loaded (buffers/clips) or volume/pan/mute/solo state.
        """
        errors = []
        live = self._live_track_ids()
        known_buses = set(self._buses)
        outputs = dict(self.track_outputs)

        for src_key, dest in outputs.items():
            try:
                if isinstance(src_key, bool):
                    raise TypeError
                src_id = int(src_key)
            except (TypeError, ValueError):
                errors.append(f"stale/invalid output source key {src_key!r}")
                continue

            if src_id not in live:
                errors.append(
                    f"stale output entry for track {src_id} (track is not live)"
                )

            dest_kind = None
            dest_id = None
            if dest is None or dest == "":
                errors.append(
                    f"type error: track {src_id} dest {dest!r} is not "
                    f"'master', int track id, or bus name"
                )
                continue
            if isinstance(dest, bool):
                errors.append(
                    f"type error: track {src_id} dest {dest!r} is not "
                    f"'master', int track id, or bus name"
                )
                continue
            if isinstance(dest, str):
                stripped = dest.strip()
                if stripped.lower() == "master":
                    dest_kind = "master"
                elif stripped.lstrip("-").isdigit():
                    dest_kind = "track"
                    dest_id = int(stripped)
                elif stripped in known_buses:
                    dest_kind = "bus"
                else:
                    errors.append(
                        f"dangling dest: track {src_id} outputs to unknown "
                        f"bus {stripped!r}"
                    )
                    continue
            elif isinstance(dest, (int, np.integer)):
                dest_kind = "track"
                dest_id = int(dest)
            else:
                errors.append(
                    f"type error: track {src_id} dest {dest!r} is not "
                    f"'master', int track id, or bus name"
                )
                continue

            if dest_kind == "track":
                if dest_id not in live:
                    errors.append(
                        f"dangling dest: track {src_id} outputs to track "
                        f"{dest_id} which is not live"
                    )
                elif self._would_create_output_cycle(src_id, dest_id):
                    errors.append(
                        f"cycle: routing graph contains a cycle involving "
                        f"track {src_id} → {dest_id}"
                    )
            elif dest_kind == "bus":
                if self._would_create_node_cycle(("t", src_id), stripped):
                    errors.append(
                        f"cycle: routing graph contains a cycle involving "
                        f"track {src_id} → {stripped!r}"
                    )

        for bus in sorted(known_buses):
            dest = self.bus_outputs.get(bus, "master")
            if dest is None or dest == "" or dest == "master":
                continue
            if isinstance(dest, bool):
                errors.append(
                    f"type error: bus {bus!r} dest {dest!r} is not "
                    f"'master', int track id, or bus name"
                )
                continue
            if isinstance(dest, str):
                stripped = dest.strip()
                if stripped.lower() == "master":
                    continue
                if stripped.lstrip("-").isdigit():
                    dest_id = int(stripped)
                    if dest_id not in live:
                        errors.append(
                            f"dangling dest: bus {bus!r} outputs to track "
                            f"{dest_id} which is not live"
                        )
                    elif self._would_create_node_cycle(("b", bus), dest_id):
                        errors.append(
                            f"cycle: routing graph contains a cycle involving "
                            f"bus {bus!r} → {dest_id}"
                        )
                elif stripped in known_buses:
                    if self._would_create_node_cycle(("b", bus), stripped):
                        errors.append(
                            f"cycle: routing graph contains a cycle involving "
                            f"bus {bus!r} → {stripped!r}"
                        )
                else:
                    errors.append(
                        f"dangling dest: bus {bus!r} outputs to unknown "
                        f"bus {stripped!r}"
                    )
            elif isinstance(dest, (int, np.integer)):
                dest_id = int(dest)
                if dest_id not in live:
                    errors.append(
                        f"dangling dest: bus {bus!r} outputs to track "
                        f"{dest_id} which is not live"
                    )
                elif self._would_create_node_cycle(("b", bus), dest_id):
                    errors.append(
                        f"cycle: routing graph contains a cycle involving "
                        f"bus {bus!r} → {dest_id}"
                    )
            else:
                errors.append(
                    f"type error: bus {bus!r} dest {dest!r} is not "
                    f"'master', int track id, or bus name"
                )

        if errors:
            raise ValueError("; ".join(errors))
        return None

    def validate_routing(self):
        """Alias of validate_graph()."""
        return self.validate_graph()

    def get_track_volume(self, track_id: int) -> float:
        """Get track volume"""
        return self.track_volumes.get(track_id, 1.0)

    def get_track_pan(self, track_id: int) -> float:
        """Get track pan"""
        return self.track_pans.get(track_id, 0.0)

    def is_track_muted(self, track_id: int) -> bool:
        """Check if track is muted"""
        return self.track_mutes.get(track_id, False)

    def is_track_soloed(self, track_id: int) -> bool:
        """Check if track is soloed"""
        return self.track_solos.get(track_id, False)

    def get_position(self) -> float:
        """Get current playback position"""
        return self.current_position

    def get_state(self):
        """Get engine state for saving"""
        return {
            "sample_rate": self.sample_rate,
            "track_volumes": self.track_volumes,
            "track_pans": self.track_pans,
            "track_mutes": self.track_mutes,
            "track_solos": self.track_solos,
            "track_outputs": self.track_outputs,
        }

    def set_state(self, state):
        """Set engine state from loaded project"""
        if "sample_rate" in state:
            self.sample_rate = state["sample_rate"]
        if "track_volumes" in state:
            self.track_volumes = state["track_volumes"]
        if "track_pans" in state:
            self.track_pans = state["track_pans"]
        if "track_mutes" in state:
            self.track_mutes = state["track_mutes"]
        if "track_solos" in state:
            self.track_solos = state["track_solos"]
        if "track_outputs" in state:
            raw = state["track_outputs"] or {}
            outputs = {}
            for key, value in raw.items():
                try:
                    kid = int(key)
                except (TypeError, ValueError):
                    kid = key
                outputs[kid] = value
            self.track_outputs = outputs


class Metronome(QObject):
    """Metronome for keeping time"""

    tick = pyqtSignal()  # Emitted on each beat

    def __init__(self, sample_rate=44100):
        super().__init__()
        self.sample_rate = sample_rate
        self.bpm = 120
        self.is_active = False
        self.beat_count = 0

        # Metronome sounds
        self.high_click = self._generate_click(1000, 0.05)  # Accent
        self.low_click = self._generate_click(800, 0.05)     # Regular

    def _generate_click(self, freq, duration):
        """Generate a click sound"""
        t = np.linspace(0, duration, int(self.sample_rate * duration))
        click = np.sin(2 * np.pi * freq * t) * np.exp(-t * 20)
        return np.column_stack((click, click)).astype(np.float32)

    def set_bpm(self, bpm: int):
        """Set BPM"""
        self.bpm = max(1, min(300, bpm))

    def get_beat_duration(self) -> float:
        """Get duration of one beat in seconds"""
        return 60.0 / self.bpm

    def get_samples_per_beat(self) -> int:
        """Get number of samples per beat"""
        return int(self.sample_rate * self.get_beat_duration())

    def get_click_for_beat(self, beat_number: int):
        """Get click sound for beat (accent on beat 0)"""
        if beat_number % 4 == 0:
            return self.high_click
        else:
            return self.low_click


class AudioExporter(QObject):
    """Export audio to file"""

    export_progress = pyqtSignal(int)  # 0-100
    export_finished = pyqtSignal(str)
    export_error = pyqtSignal(str)

    def __init__(self, engine: AudioEngine):
        super().__init__()
        self.engine = engine

    def export(self, output_path: str, format: str = "wav",
               start_time: float = 0.0, end_time: Optional[float] = None):
        """Export mixed audio to file (clip start/trim honored)."""
        try:
            sample_rate = self.engine.sample_rate
            output = self.engine.render(start_time=start_time, end_time=end_time)
            self.export_progress.emit(50)

            if not SF_AVAILABLE:
                self._write_wav_stdlib(output_path, output, sample_rate)
                self.export_progress.emit(100)
                self.export_finished.emit(output_path)
                return

            fmt = (format or "wav").lower()
            if fmt == "wav":
                sf.write(output_path, output, sample_rate, subtype="PCM_16")
            elif fmt == "mp3":
                wav_path = output_path.rsplit(".", 1)[0] + ".wav"
                sf.write(wav_path, output, sample_rate, subtype="PCM_16")
                output_path = wav_path
            elif fmt == "flac":
                sf.write(output_path, output, sample_rate)
            else:
                sf.write(output_path, output, sample_rate)

            self.export_progress.emit(100)
            self.export_finished.emit(output_path)

        except Exception as e:
            self.export_error.emit(str(e))

    def _write_wav_stdlib(self, output_path, output, sample_rate):
        data = np.clip(ensure_stereo(output), -1.0, 1.0)
        pcm = (data * 32767.0).astype(np.int16)
        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())
