"""
MIDI Clip with file-safe note persistence
"""

from typing import List, Dict
from dataclasses import dataclass, field
import uuid


@dataclass
class MidiNote:
    """A single MIDI note (file-safe; no audio arrays)."""

    pitch: int          # 0-127
    start_beat: float
    duration_beats: float
    velocity: int       # 1-127

    def to_dict(self) -> Dict:
        return {
            'pitch': int(self.pitch),
            'start_beat': float(self.start_beat),
            'duration_beats': float(self.duration_beats),
            'velocity': int(self.velocity),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'MidiNote':
        return cls(
            pitch=int(data.get('pitch', 60)),
            start_beat=float(data.get('start_beat', 0.0)),
            duration_beats=float(data.get('duration_beats', 1.0)),
            velocity=int(data.get('velocity', 100)),
        )


@dataclass
class MidiClip:
    """Represents a MIDI clip on the timeline (file-safe; no audio arrays)."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Untitled MIDI"
    track_id: int = 0
    instrument: str = "piano"
    bpm: float = 120.0
    notes: List[MidiNote] = field(default_factory=list)

    def add_note(
        self,
        pitch: int,
        start_beat: float,
        duration_beats: float,
        velocity: int = 100,
    ) -> MidiNote:
        """Append a note and return it."""
        note = MidiNote(
            pitch=int(pitch),
            start_beat=float(start_beat),
            duration_beats=float(duration_beats),
            velocity=int(velocity),
        )
        self.notes.append(note)
        return note

    @property
    def duration_beats(self) -> float:
        """Length in beats: max(start + duration) across notes, or 0 if empty."""
        if not self.notes:
            return 0.0
        return max(n.start_beat + n.duration_beats for n in self.notes)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization. Notes are plain dicts."""
        return {
            'type': 'midi',
            'id': self.id,
            'name': self.name,
            'track_id': self.track_id,
            'instrument': self.instrument,
            'bpm': self.bpm,
            'notes': [
                n.to_dict() if isinstance(n, MidiNote) else MidiNote.from_dict(n).to_dict()
                for n in self.notes
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'MidiClip':
        """Create clip from dictionary. Missing notes/instrument/bpm use defaults."""
        raw_notes = data.get('notes')
        if not raw_notes:
            notes: List[MidiNote] = []
        else:
            notes = [
                n if isinstance(n, MidiNote) else MidiNote.from_dict(n)
                for n in raw_notes
            ]
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', 'Untitled MIDI'),
            track_id=data.get('track_id', 0),
            instrument=data.get('instrument', 'piano'),
            bpm=float(data.get('bpm', 120.0)),
            notes=notes,
        )
