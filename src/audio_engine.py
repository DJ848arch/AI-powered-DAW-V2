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
except Exception:
    def _effects_apply_inserts(track_id, audio):
        """Identity fallback when the effects rack is unavailable."""
        return audio

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
        # Optional test hook: callable(track_id, audio) -> audio. None = use rack apply_inserts.
        self._insert_processor = None

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

    def unload_track(self, track_id: int):
        """Unload audio from a track (and its clips)."""
        track_id = self._coerce_track_id(track_id, {})
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
        for src, dests in list(self.track_sends.items()):
            kept = [d for d in dests if d != track_id]
            if kept:
                self.track_sends[src] = kept
            else:
                del self.track_sends[src]
            levels = self.track_send_levels.get(src)
            if levels is not None:
                levels.pop(track_id, None)
                if not levels:
                    self.track_send_levels.pop(src, None)
        self._rebuild_track_buffers()

    def clear(self):
        """Remove all loaded clips and track buffers."""
        self.clips = []
        self.track_buffers = {}
        self.master_mix = None
        self._clip_seq = 0
        self.track_outputs = {}
        self._buses = set()
        self.track_sends = {}
        self.track_send_levels = {}

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

    def _apply_inserts(self, track_id, audio):
        """On-channel insert hook (identity/dry when the rack has no DSP).

        Canonical order: clips summed on track → on-channel inserts →
        mute/solo/volume/pan → split to main output (set_track_output)
        AND post-fader sends (then send level). Inserts sit before the
        split, so they affect both the main path and sends. They are
        not applied on the bus or master in this slice.

        Tests may assign ``engine._insert_processor`` (callable
        ``(track_id, audio) -> audio``) or use ``effects_rack.set_test_insert``.
        """
        if audio is None:
            return audio
        proc = self._insert_processor
        if callable(proc):
            out = proc(track_id, audio)
            return audio if out is None else out
        return _effects_apply_inserts(track_id, audio)

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
          2. on-channel inserts (identity/dry today; ``_apply_inserts``)
          3. mute/solo/volume/pan
          4. split to main output (set_track_output) AND post-fader sends
             (send copy is then multiplied by per-send level; default 1.0)

        Inserts are ON-CHANNEL: they run before the split, so they affect
        both the main output and sends. They are not on the bus or master.

        Track output routing: after inserts, add tracks whose dest is
        another track_id into that dest buffer (before dest volume/pan),
        mix dest=master tracks through mute/solo/volume/pan into master,
        and mix dest=bus tracks through their own mute/solo/volume/pan
        into that bus (no bus fader), then sum each bus into master. A
        track routed to a track or bus is not also summed directly into
        master.

        Sends are EXTRA (in-memory only): a post-fader copy of the source
        track's own (insert-processed) clips is multiplied by send level
        and also added to each send dest. Bus send dests sum into that
        bus (no bus fader). Track send dests add into the dest buffer
        before the dest fader. The main output path is unchanged — send
        is not a replacement. Level 0 silences only the send path.
        """
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

        # Pass 1b: on-channel inserts (dry/identity today). Before fader/split.
        for tid in list(own.keys()):
            processed = self._apply_inserts(tid, own[tid])
            if processed is not None:
                own[tid] = processed

        # Pass 2: route source own-sum into dest track before dest fader.
        # Snapshot own clips so A→B only adds A's clips (one hop, no walker).
        # Named-bus dests are not track dests — they are mixed in pass 4.
        combined = {tid: arr.copy() for tid, arr in own.items()}
        for src_tid, buf in own.items():
            dest = self.get_track_output(src_tid)
            if dest == "master":
                continue
            # bool is a subclass of int — never treat True/False as a track id.
            if isinstance(dest, bool) or not isinstance(dest, (int, np.integer)):
                continue
            dest_id = int(dest)
            if dest_id not in combined:
                combined[dest_id] = np.zeros((n_frames, self.channels), dtype=np.float32)
                self._ensure_track_defaults(dest_id)
            combined[dest_id] += buf

        # Extra sends: post-fader copy of each source's own clips.
        # Track dests add into dest combined (before dest fader). Bus dests
        # are applied when buses are mixed (pass 4).
        known_buses = self._buses
        send_to_bus = []
        post_fader_own = {}

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

        for src_key, dests in self.track_sends.items():
            try:
                if isinstance(src_key, bool):
                    continue
                src_tid = int(src_key)
            except (TypeError, ValueError):
                continue
            segment = _own_post_fader(src_tid)
            if segment is None:
                continue
            src_levels = self.track_send_levels.get(src_tid) or {}
            for dest in dests or []:
                if isinstance(dest, bool):
                    continue
                level = src_levels.get(dest, 1.0)
                try:
                    level = float(level)
                except (TypeError, ValueError):
                    level = 1.0
                if not math.isfinite(level) or level <= 0.0:
                    # 0 silences only this send; invalid stuffed levels skip.
                    continue
                send_buf = segment if level == 1.0 else (segment * np.float32(level))
                if isinstance(dest, (int, np.integer)):
                    dest_id = int(dest)
                    if dest_id not in combined:
                        combined[dest_id] = np.zeros(
                            (n_frames, self.channels), dtype=np.float32
                        )
                        self._ensure_track_defaults(dest_id)
                    combined[dest_id] += send_buf
                elif isinstance(dest, str) and dest in known_buses:
                    send_to_bus.append((dest, send_buf))

        # Pass 3: tracks whose dest is master (or missing) go through
        # mute/solo/volume/pan into master.
        for track_id, buf in combined.items():
            if self.get_track_output(track_id) != "master":
                continue
            segment = self._apply_track_fader(track_id, buf, any_solo)
            if segment is None:
                continue
            mix += segment

        # Pass 4: tracks whose dest is a named bus. Source mute/solo/volume/pan
        # apply, then the bus (no fader in this slice) sums into master.
        bus_mix = {}
        for track_id, buf in combined.items():
            dest = self.get_track_output(track_id)
            if not isinstance(dest, str) or dest == "master":
                continue
            if dest not in known_buses:
                continue
            segment = self._apply_track_fader(track_id, buf, any_solo)
            if segment is None:
                continue
            if dest not in bus_mix:
                bus_mix[dest] = np.zeros((n_frames, self.channels), dtype=np.float32)
            bus_mix[dest] += segment
        for dest, segment in send_to_bus:
            if dest not in bus_mix:
                bus_mix[dest] = np.zeros((n_frames, self.channels), dtype=np.float32)
            bus_mix[dest] += segment
        for bbuf in bus_mix.values():
            mix += bbuf

        # Soft master limiter (same as the original engine)
        mix = np.tanh(mix)
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

    def _would_create_output_cycle(self, track_id: int, dest_id: int) -> bool:
        """True if routing track_id → dest_id would close a cycle.

        Walk dest_id's existing output chain (one hop at a time). If we
        reach track_id, the new edge would loop. ``"master"`` / missing
        dest ends the walk. Mix stays one-hop; this is setter-only.
        """
        seen = set()
        current = dest_id
        while True:
            if current == track_id:
                return True
            if current in seen:
                return True
            seen.add(current)
            nxt = self.get_track_output(current)
            if nxt == "master":
                return False
            try:
                current = int(nxt)
            except (TypeError, ValueError):
                return False

    def set_track_output(self, track_id: int, dest):
        """Set where a track's audio is summed.

        dest ``None`` / missing / ``"master"`` → today's mix (track sums
        into master after its own volume/pan/mute/solo). dest an int
        track id → that track's buffer (then dest fader applies). dest a
        known bus name → that bus (source fader/mute/solo apply; bus has
        no fader and mixes to master). Unknown dest is rejected.
        Self-output and multi-track cycles (0→1→0, 0→1→2→0, …) are
        rejected in this setter so the mix stays well-defined without a
        cycle walker. Buses only mix to master in this slice (no bus→track).
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
        add is idempotent. Buses mix to master with no fader in this slice.
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

    def _resolve_send_dest(self, track_id: int, dest):
        """Normalize a send dest or raise ValueError.

        dest is a known bus name or a live track id. ``"master"`` is
        rejected: the main output path already covers master, and a send
        to master would double the track. Self-send is rejected. Track
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
                return stripped
            else:
                raise ValueError(f"Unknown send dest: {dest!r}")
        elif isinstance(dest, bool):
            raise ValueError(f"Unknown send dest: {dest!r}")
        elif isinstance(dest, (int, np.integer)):
            dest_id = int(dest)
        else:
            raise ValueError(f"Unknown send dest: {dest!r}")

        if dest_id == track_id:
            raise ValueError(f"Track {track_id} cannot send to itself")
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

    def add_send(self, track_id, dest, level=1.0):
        """Add an extra send from track_id to dest (bus name or live track id).

        A send is EXTRA: the track still follows ``set_track_output`` to
        its main dest, and a post-fader copy of the track's own clips is
        multiplied by ``level`` (default 1.0 unity) and also mixed into
        ``dest``. dest cannot be ``"master"`` (main output already
        covers master). Duplicate send to the same dest is idempotent
        (no double mix; existing level is kept). Self-send is rejected.
        Live graph only here; ProjectManager persists sends in .daw 1.1.

        ``level`` must be a finite non-negative gain. 0.0 silences only
        the send path. Unknown dest is ValueError.
        """
        track_id = self._coerce_track_id(track_id, {})
        dest_norm = self._resolve_send_dest(track_id, dest)
        level = self._validate_send_level(level)
        self._ensure_track_defaults(track_id)
        sends = self.track_sends.setdefault(track_id, [])
        if dest_norm not in sends:
            sends.append(dest_norm)
            self.track_send_levels.setdefault(track_id, {})[dest_norm] = level

    def get_sends(self, track_id):
        """Return a copy of extra send dests for track_id (bus names / track ids)."""
        track_id = self._coerce_track_id(track_id, {})
        return list(self.track_sends.get(track_id, []))

    def set_send_level(self, track_id, dest, level):
        """Set per-send gain. dest must already be a send on this track.

        ``level`` is a finite non-negative gain. 0.0 silences only the
        send; the main output path is unchanged. Unknown dest, or a dest
        that is not an existing send, is ValueError.
        """
        track_id = self._coerce_track_id(track_id, {})
        dest_norm = self._resolve_send_dest(track_id, dest)
        level = self._validate_send_level(level)
        sends = self.track_sends.get(track_id) or []
        if dest_norm not in sends:
            raise ValueError(
                f"No send from track {track_id} to {dest_norm!r}"
            )
        self.track_send_levels.setdefault(track_id, {})[dest_norm] = level

    def get_send_level(self, track_id, dest):
        """Return the per-send gain (1.0 if never set). dest must be a send."""
        track_id = self._coerce_track_id(track_id, {})
        dest_norm = self._resolve_send_dest(track_id, dest)
        sends = self.track_sends.get(track_id) or []
        if dest_norm not in sends:
            raise ValueError(
                f"No send from track {track_id} to {dest_norm!r}"
            )
        return float(self.track_send_levels.get(track_id, {}).get(dest_norm, 1.0))

    def remove_send(self, track_id, dest):
        """Remove one send if present. Unknown / missing dest is a no-op."""
        track_id = self._coerce_track_id(track_id, {})
        sends = self.track_sends.get(track_id)
        if not sends:
            return
        try:
            dest_norm = self._resolve_send_dest(track_id, dest)
        except ValueError:
            if isinstance(dest, str):
                dest_norm = dest.strip()
            else:
                dest_norm = dest
        if dest_norm in sends:
            sends.remove(dest_norm)
            levels = self.track_send_levels.get(track_id)
            if levels is not None:
                levels.pop(dest_norm, None)
                if not levels:
                    self.track_send_levels.pop(track_id, None)
        if not sends:
            self.track_sends.pop(track_id, None)

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
