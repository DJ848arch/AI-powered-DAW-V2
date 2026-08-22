"""
Audio Engine with Playback Controls
Handles audio playback, mixing, and routing.

WAV clips are loaded, trimmed, and mixed honoring each clip's timeline
start (and trim/length). Playback works through sounddevice when a
device is present, and through an offline render path otherwise so
tests can verify samples without hardware.
"""

import os
import threading
import queue
import time
import wave
from pathlib import Path
from typing import Optional, List, Dict, Callable, Any, Iterable, Union

import numpy as np

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
        self._rebuild_track_buffers()

    def clear(self):
        """Remove all loaded clips and track buffers."""
        self.clips = []
        self.track_buffers = {}
        self.master_mix = None
        self._clip_seq = 0

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
        """
        mix = np.zeros((n_frames, self.channels), dtype=np.float32)
        any_solo = any(self.track_solos.values()) if self.track_solos else False
        region_end = start_sample + n_frames

        for track_id, audio, src_start in self._iter_sources(records):
            if not self._track_audible(track_id, any_solo):
                continue
            src_end = src_start + len(audio)
            ov_start = max(start_sample, src_start)
            ov_end = min(region_end, src_end)
            if ov_start >= ov_end:
                continue
            dest = ov_start - start_sample
            src = ov_start - src_start
            n = ov_end - ov_start
            segment = audio[src:src + n]
            volume = self.track_volumes.get(track_id, 1.0)
            if volume != 1.0:
                segment = segment * volume
            pan = self.track_pans.get(track_id, 0.0)
            if pan != 0.0:
                segment = apply_pan(segment, pan)
            mix[dest:dest + n] += segment

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
