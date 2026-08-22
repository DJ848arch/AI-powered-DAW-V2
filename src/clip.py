"""
Audio Clip with Cut, Copy, Paste, Trim Operations
"""

import numpy as np
import soundfile as sf
from typing import Optional, List, Dict
from dataclasses import dataclass, field
import uuid
import copy


@dataclass
class AudioClip:
    """Represents an audio clip on the timeline"""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Untitled Clip"
    track_id: int = 0
    
    # Timing
    start_time: float = 0.0  # Start time on timeline (seconds)
    duration: float = 0.0    # Duration (seconds)
    
    # Audio data
    audio_data: Optional[np.ndarray] = None  # Raw audio samples
    file_path: Optional[str] = None  # Source file path
    
    # Audio properties
    sample_rate: int = 44100
    channels: int = 2
    
    # Trim points (relative to audio_data)
    trim_start: float = 0.0  # Start trim in seconds
    trim_end: float = 0.0    # End trim in seconds (0 = no trim)
    
    # Cached waveform data for visualization
    waveform_data: Optional[np.ndarray] = None
    
    def __post_init__(self):
        """Initialize after creation"""
        if self.audio_data is not None and len(self.audio_data) > 0:
            self._update_duration()
            self._generate_waveform()
            
    @property
    def end_time(self) -> float:
        """Get end time on timeline"""
        return self.start_time + self.get_trimmed_duration()
        
    def get_trimmed_duration(self) -> float:
        """Get duration after trimming"""
        if self.trim_end > 0:
            return self.trim_end - self.trim_start
        return self.duration - self.trim_start
        
    def _update_duration(self):
        """Update duration from audio data"""
        if self.audio_data is not None:
            self.duration = len(self.audio_data) / self.sample_rate
            if self.trim_end == 0:
                self.trim_end = self.duration
                
    def _generate_waveform(self, samples: int = 1000):
        """Generate waveform data for visualization"""
        if self.audio_data is None or len(self.audio_data) == 0:
            self.waveform_data = None
            return
            
        # Get mono representation
        if len(self.audio_data.shape) > 1:
            mono = np.mean(self.audio_data, axis=1)
        else:
            mono = self.audio_data
            
        # Resample to target samples
        if len(mono) > samples:
            # Downsample
            indices = np.linspace(0, len(mono) - 1, samples, dtype=int)
            self.waveform_data = mono[indices]
        else:
            self.waveform_data = mono
            
    def get_audio_segment(self, start: float, end: float) -> np.ndarray:
        """Get audio segment in seconds (relative to clip start)"""
        if self.audio_data is None:
            return np.array([])
            
        # Convert to samples
        start_sample = int((self.trim_start + start) * self.sample_rate)
        end_sample = int((self.trim_start + end) * self.sample_rate)
        
        # Clamp to bounds
        start_sample = max(0, min(start_sample, len(self.audio_data)))
        end_sample = max(0, min(end_sample, len(self.audio_data)))
        
        if start_sample >= end_sample:
            return np.array([])
            
        return self.audio_data[start_sample:end_sample]
        
    def get_full_audio(self) -> np.ndarray:
        """Get full audio data (respecting trim)"""
        if self.audio_data is None:
            return np.array([])
            
        start_sample = int(self.trim_start * self.sample_rate)
        end_sample = int(self.trim_end * self.sample_rate) if self.trim_end > 0 else len(self.audio_data)
        
        start_sample = max(0, min(start_sample, len(self.audio_data)))
        end_sample = max(0, min(end_sample, len(self.audio_data)))
        
        return self.audio_data[start_sample:end_sample]
        
    def copy(self) -> 'AudioClip':
        """Create a copy of this clip"""
        new_clip = AudioClip(
            name=f"{self.name} (copy)",
            track_id=self.track_id,
            audio_data=copy.deepcopy(self.audio_data) if self.audio_data is not None else None,
            file_path=self.file_path,
            sample_rate=self.sample_rate,
            channels=self.channels,
            trim_start=self.trim_start,
            trim_end=self.trim_end
        )
        new_clip._update_duration()
        new_clip._generate_waveform()
        return new_clip
        
    def trim(self, start: float, end: float):
        """Trim clip to time range (relative to clip)"""
        self.trim_start = max(0, start)
        self.trim_end = min(self.duration, end) if end > 0 else self.duration
        self._generate_waveform()
        
    def split(self, time: float) -> Optional['AudioClip']:
        """Split clip at time, returns new clip with second half"""
        if time <= 0 or time >= self.get_trimmed_duration():
            return None
            
        # Create second clip
        second_clip = self.copy()
        second_clip.start_time = self.start_time + time
        second_clip.trim_start = self.trim_start + time
        second_clip.trim_end = self.trim_end
        
        # Trim first clip
        self.trim_end = self.trim_start + time
        
        return second_clip
        
    def fade_in(self, duration: float):
        """Apply fade in"""
        if self.audio_data is None or duration <= 0:
            return
            
        samples = int(duration * self.sample_rate)
        samples = min(samples, len(self.audio_data))
        
        fade = np.linspace(0, 1, samples)
        self.audio_data[:samples] *= fade.reshape(-1, 1) if len(self.audio_data.shape) > 1 else fade
        
    def fade_out(self, duration: float):
        """Apply fade out"""
        if self.audio_data is None or duration <= 0:
            return
            
        samples = int(duration * self.sample_rate)
        samples = min(samples, len(self.audio_data))
        
        fade = np.linspace(1, 0, samples)
        self.audio_data[-samples:] *= fade.reshape(-1, 1) if len(self.audio_data.shape) > 1 else fade
        
    def normalize(self, target_db: float = -3.0):
        """Normalize audio to target dB"""
        if self.audio_data is None or len(self.audio_data) == 0:
            return
            
        peak = np.max(np.abs(self.audio_data))
        if peak > 0:
            target_linear = 10 ** (target_db / 20)
            gain = target_linear / peak
            self.audio_data *= gain
            
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'name': self.name,
            'track_id': self.track_id,
            'start_time': self.start_time,
            'duration': self.duration,
            'file_path': self.file_path,
            'sample_rate': self.sample_rate,
            'channels': self.channels,
            'trim_start': self.trim_start,
            'trim_end': self.trim_end
        }
        
    @classmethod
    def from_dict(cls, data: Dict) -> 'AudioClip':
        """Create clip from dictionary"""
        clip = cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', 'Untitled Clip'),
            track_id=data.get('track_id', 0),
            start_time=data.get('start_time', 0.0),
            duration=data.get('duration', 0.0),
            file_path=data.get('file_path'),
            sample_rate=data.get('sample_rate', 44100),
            channels=data.get('channels', 2),
            trim_start=data.get('trim_start', 0.0),
            trim_end=data.get('trim_end', 0.0)
        )
        
        # Load audio if file exists
        if clip.file_path:
            try:
                clip = cls.from_file(clip.file_path)
                # Restore properties
                clip.id = data.get('id', str(uuid.uuid4()))
                clip.name = data.get('name', 'Untitled Clip')
                clip.track_id = data.get('track_id', 0)
                clip.start_time = data.get('start_time', 0.0)
                clip.trim_start = data.get('trim_start', 0.0)
                clip.trim_end = data.get('trim_end', 0.0)
            except:
                pass
                
        return clip
        
    @classmethod
    def from_file(cls, file_path: str, name: str = None) -> 'AudioClip':
        """Create clip from audio file"""
        audio_data, sample_rate = sf.read(file_path, dtype='float32')
        
        # Ensure stereo
        if len(audio_data.shape) == 1:
            audio_data = np.column_stack((audio_data, audio_data))
        elif audio_data.shape[1] == 1:
            audio_data = np.column_stack((audio_data[:, 0], audio_data[:, 0]))
            
        clip = cls(
            name=name or file_path.split('/')[-1].split('\\')[-1],
            audio_data=audio_data,
            file_path=file_path,
            sample_rate=sample_rate,
            channels=audio_data.shape[1] if len(audio_data.shape) > 1 else 1
        )
        
        clip._update_duration()
        clip._generate_waveform()
        
        return clip


class ClipManager:
    """Manages clip operations"""
    
    def __init__(self):
        self.clipboard: List[AudioClip] = []
        self.undo_stack: List[Dict] = []
        self.redo_stack: List[Dict] = []
        
    def cut_clip(self, clip: AudioClip, time: float) -> Optional[AudioClip]:
        """Cut clip at time"""
        return clip.split(time - clip.start_time)
        
    def copy_clip(self, clip: AudioClip):
        """Copy clip to clipboard"""
        self.clipboard = [clip.copy()]
        
    def paste_clip(self, track_id: int, time: float) -> Optional[AudioClip]:
        """Paste clip from clipboard"""
        if not self.clipboard:
            return None
            
        new_clip = self.clipboard[0].copy()
        new_clip.track_id = track_id
        new_clip.start_time = time
        return new_clip
        
    def duplicate_clip(self, clip: AudioClip) -> AudioClip:
        """Duplicate a clip"""
        new_clip = clip.copy()
        new_clip.start_time = clip.end_time + 0.1  # Small gap
        return new_clip
        
    def merge_clips(self, clips: List[AudioClip]) -> Optional[AudioClip]:
        """Merge multiple clips into one"""
        if not clips:
            return None
            
        if len(clips) == 1:
            return clips[0].copy()
            
        # Sort by start time
        clips = sorted(clips, key=lambda c: c.start_time)
        
        # Calculate total duration
        total_duration = clips[-1].end_time - clips[0].start_time
        
        # Create merged audio
        sample_rate = clips[0].sample_rate
        total_samples = int(total_duration * sample_rate)
        merged = np.zeros((total_samples, 2), dtype=np.float32)
        
        for clip in clips:
            offset = int((clip.start_time - clips[0].start_time) * sample_rate)
            audio = clip.get_full_audio()
            
            if offset + len(audio) <= len(merged):
                merged[offset:offset + len(audio)] += audio
                
        # Create new clip
        merged_clip = AudioClip(
            name="Merged Clip",
            audio_data=merged,
            sample_rate=sample_rate,
            start_time=clips[0].start_time
        )
        
        return merged_clip
        
    def crossfade_clips(self, clip1: AudioClip, clip2: AudioClip, 
                       duration: float = 0.5) -> AudioClip:
        """Crossfade two clips"""
        # Get audio
        audio1 = clip1.get_full_audio()
        audio2 = clip2.get_full_audio()
        
        # Calculate overlap samples
        overlap_samples = int(duration * clip1.sample_rate)
        
        # Create crossfade curves
        fade_out = np.linspace(1, 0, overlap_samples)
        fade_in = np.linspace(0, 1, overlap_samples)
        
        # Apply fades
        if len(audio1) >= overlap_samples:
            audio1[-overlap_samples:] *= fade_out.reshape(-1, 1)
        if len(audio2) >= overlap_samples:
            audio2[:overlap_samples] *= fade_in.reshape(-1, 1)
            
        # Merge
        merged = np.vstack([audio1, audio2[overlap_samples:]])
        
        # Create new clip
        return AudioClip(
            name="Crossfaded Clip",
            audio_data=merged,
            sample_rate=clip1.sample_rate,
            start_time=clip1.start_time
        )
        
    def time_stretch(self, clip: AudioClip, ratio: float) -> AudioClip:
        """Time stretch audio (simple resampling)"""
        if clip.audio_data is None:
            return clip.copy()
            
        # Simple resampling (not high quality, but functional)
        from scipy import signal
        
        new_length = int(len(clip.audio_data) / ratio)
        resampled = signal.resample(clip.audio_data, new_length)
        
        new_clip = AudioClip(
            name=f"{clip.name} (stretched)",
            audio_data=resampled,
            sample_rate=clip.sample_rate,
            start_time=clip.start_time
        )
        
        return new_clip
        
    def pitch_shift(self, clip: AudioClip, semitones: float) -> AudioClip:
        """Pitch shift audio using librosa"""
        try:
            import librosa
            
            if clip.audio_data is None:
                return clip.copy()
                
            # Convert to mono for processing
            if len(clip.audio_data.shape) > 1:
                mono = np.mean(clip.audio_data, axis=1)
            else:
                mono = clip.audio_data
                
            # Pitch shift
            shifted = librosa.effects.pitch_shift(
                mono, sr=clip.sample_rate, n_steps=semitones
            )
            
            # Convert back to stereo
            shifted_stereo = np.column_stack((shifted, shifted))
            
            new_clip = AudioClip(
                name=f"{clip.name} (pitched)",
                audio_data=shifted_stereo,
                sample_rate=clip.sample_rate,
                start_time=clip.start_time
            )
            
            return new_clip
            
        except ImportError:
            # Fallback: just return copy
            return clip.copy()
