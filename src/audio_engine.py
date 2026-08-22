"""
Audio Engine with Playback Controls
Handles audio playback, mixing, and routing
"""

import numpy as np
import soundfile as sf
import sounddevice as sd
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import QMessageBox
from typing import Optional, List, Dict, Callable
import threading
import queue


class AudioEngine(QObject):
    """Main audio engine for playback and mixing"""
    
    # Signals
    playback_started = pyqtSignal()
    playback_paused = pyqtSignal()
    playback_stopped = pyqtSignal()
    playback_position_changed = pyqtSignal(float)
    playback_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self, sample_rate=44100, buffer_size=1024):
        super().__init__()
        
        self.sample_rate = sample_rate
        self.buffer_size = buffer_size
        self.channels = 2
        
        # Playback state
        self.is_playing = False
        self.is_paused = False
        self.current_position = 0.0  # seconds
        self.start_position = 0.0
        
        # Audio data
        self.master_mix = None  # Mixed audio buffer
        self.track_buffers = {}  # track_id: audio_data
        
        # Track settings
        self.track_volumes = {}  # track_id: volume (0.0 - 1.0)
        self.track_pans = {}     # track_id: pan (-1.0 to 1.0)
        self.track_mutes = {}    # track_id: muted
        self.track_solos = {}    # track_id: soloed
        
        # Audio stream
        self.stream = None
        self.audio_queue = queue.Queue()
        self.audio_thread = None
        
        # Callbacks
        self.position_callbacks = []
        
        # Timer for UI updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_position)
        self.update_timer.setInterval(50)  # 20 FPS
        
    def initialize(self):
        """Initialize audio engine"""
        try:
            # Check available audio devices
            devices = sd.query_devices()
            default_output = sd.query_devices(kind='output')
            print(f"Audio engine initialized: {default_output['name']}")
            return True
        except Exception as e:
            self.error_occurred.emit(f"Failed to initialize audio: {str(e)}")
            return False
            
    def load_audio(self, track_id: int, audio_data: np.ndarray):
        """Load audio data for a track"""
        # Ensure stereo
        if len(audio_data.shape) == 1:
            audio_data = np.column_stack((audio_data, audio_data))
        elif audio_data.shape[1] == 1:
            audio_data = np.column_stack((audio_data[:, 0], audio_data[:, 0]))
            
        self.track_buffers[track_id] = audio_data.astype(np.float32)
        
        # Initialize track settings
        if track_id not in self.track_volumes:
            self.track_volumes[track_id] = 1.0
        if track_id not in self.track_pans:
            self.track_pans[track_id] = 0.0
        if track_id not in self.track_mutes:
            self.track_mutes[track_id] = False
        if track_id not in self.track_solos:
            self.track_solos[track_id] = False
            
    def unload_track(self, track_id: int):
        """Unload audio from a track"""
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
            
    def play(self, start_position: float = 0.0):
        """Start playback"""
        if self.is_playing and not self.is_paused:
            return
            
        self.start_position = start_position
        self.current_position = start_position
        
        try:
            # Create audio stream
            self.stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                blocksize=self.buffer_size,
                callback=self._audio_callback,
                dtype=np.float32
            )
            
            self.stream.start()
            self.is_playing = True
            self.is_paused = False
            self.update_timer.start()
            self.playback_started.emit()
            
        except Exception as e:
            self.error_occurred.emit(f"Playback error: {str(e)}")
            
    def pause(self):
        """Pause playback"""
        if not self.is_playing or self.is_paused:
            return
            
        self.is_paused = True
        self.update_timer.stop()
        
        if self.stream:
            self.stream.stop()
            
        self.playback_paused.emit()
        
    def stop(self):
        """Stop playback"""
        if not self.is_playing:
            return
            
        self.is_playing = False
        self.is_paused = False
        self.current_position = 0.0
        self.update_timer.stop()
        
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            
        self.playback_stopped.emit()
        
    def seek(self, position: float):
        """Seek to position in seconds"""
        self.current_position = max(0.0, position)
        self.playback_position_changed.emit(self.current_position)
        
    def _audio_callback(self, outdata, frames, time_info, status):
        """Audio callback for sounddevice"""
        if status:
            print(f"Audio callback status: {status}")
            
        # Calculate sample positions
        start_sample = int(self.current_position * self.sample_rate)
        end_sample = start_sample + frames
        
        # Mix tracks
        mix = np.zeros((frames, self.channels), dtype=np.float32)
        
        # Check if any track is soloed
        any_solo = any(self.track_solos.values()) if self.track_solos else False
        
        for track_id, audio_data in self.track_buffers.items():
            # Skip muted tracks (unless soloed)
            if self.track_mutes.get(track_id, False):
                if not any_solo or not self.track_solos.get(track_id, False):
                    continue
                    
            # Skip non-soloed tracks if any track is soloed
            if any_solo and not self.track_solos.get(track_id, False):
                continue
                
            # Get track audio segment
            if start_sample < len(audio_data):
                track_end = min(end_sample, len(audio_data))
                segment = audio_data[start_sample:track_end]
                
                # Pad if necessary
                if len(segment) < frames:
                    padding = np.zeros((frames - len(segment), self.channels))
                    segment = np.vstack((segment, padding))
                    
                # Apply volume
                volume = self.track_volumes.get(track_id, 1.0)
                segment = segment * volume
                
                # Apply pan
                pan = self.track_pans.get(track_id, 0.0)
                if pan != 0.0:
                    # Pan law: -1 = full left, 0 = center, 1 = full right
                    left_gain = min(1.0, 1.0 - pan)
                    right_gain = min(1.0, 1.0 + pan)
                    segment[:, 0] *= left_gain
                    segment[:, 1] *= right_gain
                    
                mix += segment
                
        # Apply master limiter (soft clipping)
        mix = np.tanh(mix)
        
        # Output
        outdata[:] = mix
        
        # Update position
        self.current_position += frames / self.sample_rate
        
        # Check if playback finished
        max_length = max(len(buf) for buf in self.track_buffers.values()) if self.track_buffers else 0
        if start_sample >= max_length:
            self.stop()
            self.playback_finished.emit()
            
    def _update_position(self):
        """Update position for UI"""
        self.playback_position_changed.emit(self.current_position)
        
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
            'sample_rate': self.sample_rate,
            'track_volumes': self.track_volumes,
            'track_pans': self.track_pans,
            'track_mutes': self.track_mutes,
            'track_solos': self.track_solos
        }
        
    def set_state(self, state):
        """Set engine state from loaded project"""
        if 'sample_rate' in state:
            self.sample_rate = state['sample_rate']
        if 'track_volumes' in state:
            self.track_volumes = state['track_volumes']
        if 'track_pans' in state:
            self.track_pans = state['track_pans']
        if 'track_mutes' in state:
            self.track_mutes = state['track_mutes']
        if 'track_solos' in state:
            self.track_solos = state['track_solos']


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
        
    def export(self, output_path: str, format: str = 'wav', 
               start_time: float = 0.0, end_time: Optional[float] = None):
        """Export mixed audio to file"""
        try:
            # Calculate export parameters
            sample_rate = self.engine.sample_rate
            
            # Determine max length
            if end_time is None:
                max_length = max(len(buf) for buf in self.engine.track_buffers.values())
                end_time = max_length / sample_rate
                
            start_sample = int(start_time * sample_rate)
            end_sample = int(end_time * sample_rate)
            total_samples = end_sample - start_sample
            
            # Create output buffer
            output = np.zeros((total_samples, 2), dtype=np.float32)
            
            # Mix tracks
            any_solo = any(self.engine.track_solos.values()) if self.engine.track_solos else False
            
            chunk_size = 44100  # Process in 1-second chunks
            for i in range(0, total_samples, chunk_size):
                chunk_end = min(i + chunk_size, total_samples)
                actual_chunk_size = chunk_end - i
                
                chunk_mix = np.zeros((actual_chunk_size, 2), dtype=np.float32)
                
                for track_id, audio_data in self.engine.track_buffers.items():
                    # Skip muted tracks
                    if self.engine.track_mutes.get(track_id, False):
                        if not any_solo or not self.engine.track_solos.get(track_id, False):
                            continue
                            
                    # Skip non-soloed tracks if any track is soloed
                    if any_solo and not self.engine.track_solos.get(track_id, False):
                        continue
                        
                    # Get segment
                    track_start = start_sample + i
                    track_end = min(track_start + actual_chunk_size, len(audio_data))
                    
                    if track_start < len(audio_data):
                        segment = audio_data[track_start:track_end]
                        
                        # Pad if necessary
                        if len(segment) < actual_chunk_size:
                            padding = np.zeros((actual_chunk_size - len(segment), 2))
                            segment = np.vstack((segment, padding))
                            
                        # Apply volume
                        volume = self.engine.track_volumes.get(track_id, 1.0)
                        segment = segment * volume
                        
                        # Apply pan
                        pan = self.engine.track_pans.get(track_id, 0.0)
                        if pan != 0.0:
                            left_gain = min(1.0, 1.0 - pan)
                            right_gain = min(1.0, 1.0 + pan)
                            segment[:, 0] *= left_gain
                            segment[:, 1] *= right_gain
                            
                        chunk_mix += segment
                        
                # Apply master limiter
                chunk_mix = np.tanh(chunk_mix)
                output[i:chunk_end] = chunk_mix
                
                # Emit progress
                progress = int((i / total_samples) * 100)
                self.export_progress.emit(progress)
                
            # Write to file
            if format.lower() == 'wav':
                sf.write(output_path, output, sample_rate, subtype='PCM_16')
            elif format.lower() == 'mp3':
                # MP3 requires additional handling
                # For now, write as WAV and let user convert
                wav_path = output_path.rsplit('.', 1)[0] + '.wav'
                sf.write(wav_path, output, sample_rate, subtype='PCM_16')
                output_path = wav_path
            elif format.lower() == 'flac':
                sf.write(output_path, output, sample_rate)
            else:
                sf.write(output_path, output, sample_rate)
                
            self.export_progress.emit(100)
            self.export_finished.emit(output_path)
            
        except Exception as e:
            self.export_error.emit(str(e))
