"""
Audio Analysis Pipeline for v1.1 Architecture
Provides BPM detection, key analysis, energy curves, and onset detection
"""

import os
import numpy as np
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt6.QtCore import QObject, pyqtSignal, QThread
import warnings

# Optional imports - will gracefully degrade if not available
try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    warnings.warn("librosa not available - audio analysis will be limited")

try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except ImportError:
    SOUNDFILE_AVAILABLE = False


@dataclass
class AnalysisResult:
    """Complete audio analysis results"""
    file_path: str = ""
    duration_seconds: float = 0.0
    sample_rate: int = 44100
    
    # Rhythm analysis
    bpm: float = 0.0
    bpm_confidence: float = 0.0
    beat_positions: List[float] = field(default_factory=list)
    
    # Key analysis
    key: str = ""  # e.g., "C major", "A minor"
    key_confidence: float = 0.0
    key_alternatives: List[Dict] = field(default_factory=list)
    
    # Energy analysis
    energy_curve: List[float] = field(default_factory=list)
    rms_energy: float = 0.0
    dynamic_range_db: float = 0.0
    
    # Onset detection
    onset_times: List[float] = field(default_factory=list)
    onset_strengths: List[float] = field(default_factory=list)
    
    # Spectral features
    spectral_centroid: List[float] = field(default_factory=list)
    spectral_rolloff: List[float] = field(default_factory=list)
    spectral_bandwidth: List[float] = field(default_factory=list)
    
    # Transcription data
    notes: List[Dict] = field(default_factory=list)  # pitch, velocity, time, duration
    chords: List[Dict] = field(default_factory=list)  # root, quality, time
    
    # Metadata
    analyzed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    analysis_version: str = "1.0"
    error: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "file_path": self.file_path,
            "duration_seconds": self.duration_seconds,
            "sample_rate": self.sample_rate,
            "bpm": self.bpm,
            "bpm_confidence": self.bpm_confidence,
            "beat_positions": self.beat_positions,
            "key": self.key,
            "key_confidence": self.key_confidence,
            "key_alternatives": self.key_alternatives,
            "energy_curve": self.energy_curve,
            "rms_energy": self.rms_energy,
            "dynamic_range_db": self.dynamic_range_db,
            "onset_times": self.onset_times,
            "onset_strengths": self.onset_strengths,
            "spectral_centroid": self.spectral_centroid,
            "spectral_rolloff": self.spectral_rolloff,
            "spectral_bandwidth": self.spectral_bandwidth,
            "notes": self.notes,
            "chords": self.chords,
            "analyzed_at": self.analyzed_at,
            "analysis_version": self.analysis_version,
            "error": self.error
        }


class AudioAnalyzer(QObject):
    """Audio analysis using librosa for transcription"""
    
    # Signals
    analysis_progress = pyqtSignal(str, int)  # file_path, progress_percent
    analysis_complete = pyqtSignal(str, object)  # file_path, AnalysisResult
    analysis_error = pyqtSignal(str, str)  # file_path, error_message
    
    def __init__(self, max_workers: int = 4):
        super().__init__()
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._active_tasks: Dict[str, Any] = {}
        
    def analyze_file(self, file_path: str, 
                     callback: Callable = None) -> AnalysisResult:
        """Analyze a single audio file"""
        if not LIBROSA_AVAILABLE:
            result = AnalysisResult(
                file_path=file_path,
                error="librosa not available - cannot analyze audio"
            )
            if callback:
                callback(result)
            return result
        
        try:
            self.analysis_progress.emit(file_path, 10)
            
            # Load audio
            y, sr = librosa.load(file_path, sr=None, mono=True)
            duration = librosa.get_duration(y=y, sr=sr)
            
            result = AnalysisResult(
                file_path=file_path,
                duration_seconds=duration,
                sample_rate=sr
            )
            
            self.analysis_progress.emit(file_path, 30)
            
            # BPM detection
            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            result.bpm = float(tempo)
            result.beat_positions = librosa.frames_to_time(beat_frames, sr=sr).tolist()
            
            # Estimate confidence based on onset strength
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            result.bpm_confidence = float(np.mean(onset_env) / np.max(onset_env)) if np.max(onset_env) > 0 else 0.5
            
            self.analysis_progress.emit(file_path, 50)
            
            # Key detection using chroma
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
            result.key, result.key_confidence = self._detect_key(chroma)
            
            self.analysis_progress.emit(file_path, 60)
            
            # Energy analysis
            rms = librosa.feature.rms(y=y)[0]
            result.rms_energy = float(np.mean(rms))
            result.energy_curve = rms.tolist()
            result.dynamic_range_db = float(20 * np.log10(np.max(rms) / (np.min(rms) + 1e-10)))
            
            self.analysis_progress.emit(file_path, 70)
            
            # Onset detection
            onset_frames = librosa.onset.onset_detect(y=y, sr=sr, onset_envelope=onset_env)
            result.onset_times = librosa.frames_to_time(onset_frames, sr=sr).tolist()
            result.onset_strengths = [float(onset_env[f]) for f in onset_frames if f < len(onset_env)]
            
            self.analysis_progress.emit(file_path, 80)
            
            # Spectral features
            result.spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0].tolist()
            result.spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0].tolist()
            result.spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0].tolist()
            
            self.analysis_progress.emit(file_path, 90)
            
            # Basic pitch detection (simplified)
            result.notes = self._extract_notes(y, sr)
            
            self.analysis_progress.emit(file_path, 100)
            
            if callback:
                callback(result)
            self.analysis_complete.emit(file_path, result)
            
            return result
            
        except Exception as e:
            result = AnalysisResult(
                file_path=file_path,
                error=str(e)
            )
            self.analysis_error.emit(file_path, str(e))
            if callback:
                callback(result)
            return result
    
    def analyze_async(self, file_path: str):
        """Analyze file asynchronously"""
        future = self._executor.submit(self.analyze_file, file_path)
        self._active_tasks[file_path] = future
        return future
    
    def analyze_batch(self, file_paths: List[str]) -> Dict[str, AnalysisResult]:
        """Analyze multiple files in parallel"""
        results = {}
        futures = {self._executor.submit(self.analyze_file, fp): fp for fp in file_paths}
        
        for future in as_completed(futures):
            file_path = futures[future]
            try:
                result = future.result()
                results[file_path] = result
            except Exception as e:
                results[file_path] = AnalysisResult(
                    file_path=file_path,
                    error=str(e)
                )
        
        return results
    
    def _detect_key(self, chroma: np.ndarray) -> tuple:
        """Detect musical key from chromagram"""
        # Simple key detection using Krumhansl-Schmuckler profiles
        # This is a simplified version
        
        keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
        
        # Average chroma across time
        chroma_avg = np.mean(chroma, axis=1)
        
        best_score = -np.inf
        best_key = "Unknown"
        
        for i, key in enumerate(keys):
            # Rotate profiles to match key
            major_rotated = np.roll(major_profile, i)
            minor_rotated = np.roll(minor_profile, i)
            
            # Calculate correlation
            major_score = np.corrcoef(chroma_avg, major_rotated)[0, 1]
            minor_score = np.corrcoef(chroma_avg, minor_rotated)[0, 1]
            
            if major_score > best_score:
                best_score = major_score
                best_key = f"{key} major"
            
            if minor_score > best_score:
                best_score = minor_score
                best_key = f"{key} minor"
        
        confidence = max(0, min(1, (best_score + 1) / 2))  # Normalize to 0-1
        return best_key, confidence
    
    def _extract_notes(self, y: np.ndarray, sr: int) -> List[Dict]:
        """Extract note information from audio"""
        notes = []
        
        try:
            # Use piptrack for pitch detection
            pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
            
            # Extract note onsets and pitches
            onset_frames = librosa.onset.onset_detect(y=y, sr=sr)
            
            for onset_frame in onset_frames[:50]:  # Limit to first 50 notes
                if onset_frame < pitches.shape[1]:
                    # Find the pitch with maximum magnitude at this frame
                    pitch_idx = np.argmax(magnitudes[:, onset_frame])
                    pitch = pitches[pitch_idx, onset_frame]
                    
                    if pitch > 0:
                        # Convert to MIDI note number
                        midi_note = int(librosa.hz_to_midi(pitch))
                        time = librosa.frames_to_time(onset_frame, sr=sr)
                        velocity = int(min(127, magnitudes[pitch_idx, onset_frame] * 127 / np.max(magnitudes)))
                        
                        notes.append({
                            "pitch": midi_note,
                            "velocity": velocity,
                            "time": float(time),
                            "duration": 0.25  # Default duration
                        })
        except Exception as e:
            # Graceful degradation
            pass
        
        return notes
    
    def cancel_analysis(self, file_path: str):
        """Cancel ongoing analysis"""
        if file_path in self._active_tasks:
            future = self._active_tasks.pop(file_path)
            future.cancel()
    
    def shutdown(self):
        """Shutdown the thread pool"""
        self._executor.shutdown(wait=True)


class BuildFromStemWorkflow(QObject):
    """Workflow: Import → Analyze → Pass to Producer"""
    
    # Signals
    stem_imported = pyqtSignal(str)  # file_path
    stem_analyzed = pyqtSignal(str, object)  # file_path, AnalysisResult
    stem_ready = pyqtSignal(str, object)  # file_path, AnalysisResult
    workflow_error = pyqtSignal(str, str)  # file_path, error
    
    def __init__(self, analyzer: AudioAnalyzer = None):
        super().__init__()
        self.analyzer = analyzer or AudioAnalyzer()
        self._stems: Dict[str, Dict] = {}  # file_path -> {status, result}
        
    def import_stem(self, file_path: str) -> bool:
        """Import a stem file and start analysis"""
        try:
            if not os.path.exists(file_path):
                self.workflow_error.emit(file_path, "File not found")
                return False
            
            self._stems[file_path] = {
                "status": "imported",
                "result": None
            }
            
            self.stem_imported.emit(file_path)
            
            # Start analysis
            self.analyzer.analysis_complete.connect(self._on_analysis_complete)
            self.analyzer.analyze_async(file_path)
            
            return True
            
        except Exception as e:
            self.workflow_error.emit(file_path, str(e))
            return False
    
    def _on_analysis_complete(self, file_path: str, result: AnalysisResult):
        """Handle analysis completion"""
        if file_path in self._stems:
            self._stems[file_path]["status"] = "analyzed"
            self._stems[file_path]["result"] = result
            
            self.stem_analyzed.emit(file_path, result)
            self.stem_ready.emit(file_path, result)
    
    def get_stem_data(self, file_path: str) -> Optional[Dict]:
        """Get stem data"""
        return self._stems.get(file_path)
    
    def get_all_stems(self) -> Dict[str, Dict]:
        """Get all stem data"""
        return self._stems.copy()
    
    def create_producer_plan(self, file_path: str) -> Dict:
        """Create production plan from analyzed stem"""
        stem_data = self._stems.get(file_path)
        if not stem_data or not stem_data.get("result"):
            return {}
        
        result = stem_data["result"]
        
        return {
            "source_file": file_path,
            "tempo_bpm": result.bpm,
            "key": result.key,
            "duration_seconds": result.duration_seconds,
            "suggested_sections": self._generate_sections(result),
            "energy_profile": result.energy_curve,
            "onset_data": result.onset_times,
            "notes": result.notes
        }
    
    def _generate_sections(self, result: AnalysisResult) -> List[Dict]:
        """Generate suggested song sections from analysis"""
        sections = []
        duration = result.duration_seconds
        
        if duration < 30:
            # Short sample - single section
            sections.append({
                "name": "full",
                "start": 0.0,
                "end": duration,
                "type": "loop"
            })
        else:
            # Try to detect sections based on energy changes
            if result.energy_curve:
                # Simple section detection based on energy
                energy_array = np.array(result.energy_curve)
                
                # Find energy peaks and valleys
                from scipy.signal import find_peaks
                peaks, _ = find_peaks(energy_array, distance=len(energy_array)//10)
                
                if len(peaks) >= 3:
                    # Create intro, build, drop structure
                    sections = [
                        {"name": "intro", "start": 0.0, "end": duration * 0.2, "energy": "low"},
                        {"name": "build", "start": duration * 0.2, "end": duration * 0.4, "energy": "rising"},
                        {"name": "drop", "start": duration * 0.4, "end": duration * 0.7, "energy": "high"},
                        {"name": "outro", "start": duration * 0.7, "end": duration, "energy": "falling"}
                    ]
                else:
                    # Simple two-part structure
                    sections = [
                        {"name": "a", "start": 0.0, "end": duration * 0.5, "energy": "medium"},
                        {"name": "b", "start": duration * 0.5, "end": duration, "energy": "medium"}
                    ]
            else:
                # Default sections
                sections = [
                    {"name": "main", "start": 0.0, "end": duration, "energy": "medium"}
                ]
        
        return sections
