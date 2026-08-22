"""
Selection Model - Selection management for v1.1 Architecture
Manages track, time, and clip selections with scoped tasks
"""

from typing import List, Set, Optional, Dict, Any, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import json
from PyQt6.QtCore import QObject, pyqtSignal


class SelectionType(Enum):
    TRACKS = "tracks"
    TIME_RANGE = "time_range"
    CLIPS = "clips"
    MIXED = "mixed"
    EMPTY = "empty"


@dataclass
class TimeRange:
    """Time range selection"""
    start_beat: float = 0.0
    end_beat: float = 0.0
    start_time_seconds: float = 0.0
    end_time_seconds: float = 0.0
    
    def duration_beats(self) -> float:
        return self.end_beat - self.start_beat
    
    def duration_seconds(self) -> float:
        return self.end_time_seconds - self.start_time_seconds
    
    def contains_beat(self, beat: float) -> bool:
        return self.start_beat <= beat <= self.end_beat
    
    def to_dict(self) -> Dict:
        return {
            "start_beat": self.start_beat,
            "end_beat": self.end_beat,
            "start_time_seconds": self.start_time_seconds,
            "end_time_seconds": self.end_time_seconds
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TimeRange':
        return cls(
            start_beat=data.get("start_beat", 0.0),
            end_beat=data.get("end_beat", 0.0),
            start_time_seconds=data.get("start_time_seconds", 0.0),
            end_time_seconds=data.get("end_time_seconds", 0.0)
        )


@dataclass
class Selection:
    """Complete selection state"""
    track_ids: Set[str] = field(default_factory=set)
    time_range: Optional[TimeRange] = None
    clip_ids: Set[str] = field(default_factory=set)
    selection_type: SelectionType = SelectionType.EMPTY
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def is_empty(self) -> bool:
        return (not self.track_ids and 
                not self.clip_ids and 
                self.time_range is None)
    
    def has_tracks(self) -> bool:
        return len(self.track_ids) > 0
    
    def has_clips(self) -> bool:
        return len(self.clip_ids) > 0
    
    def has_time_range(self) -> bool:
        return self.time_range is not None
    
    def get_type(self) -> SelectionType:
        if self.is_empty():
            return SelectionType.EMPTY
        has_tracks = self.has_tracks()
        has_clips = self.has_clips()
        has_time = self.has_time_range()
        
        if has_tracks and has_clips and has_time:
            return SelectionType.MIXED
        elif has_clips:
            return SelectionType.CLIPS
        elif has_tracks:
            return SelectionType.TRACKS
        elif has_time:
            return SelectionType.TIME_RANGE
        return SelectionType.EMPTY
    
    def to_dict(self) -> Dict:
        return {
            "track_ids": list(self.track_ids),
            "time_range": self.time_range.to_dict() if self.time_range else None,
            "clip_ids": list(self.clip_ids),
            "selection_type": self.selection_type.value,
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Selection':
        return cls(
            track_ids=set(data.get("track_ids", [])),
            time_range=TimeRange.from_dict(data["time_range"]) if data.get("time_range") else None,
            clip_ids=set(data.get("clip_ids", [])),
            selection_type=SelectionType(data.get("selection_type", "empty")),
            metadata=data.get("metadata", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )
    
    def serialize(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def deserialize(cls, data: str) -> 'Selection':
        """Deserialize from JSON string"""
        return cls.from_dict(json.loads(data))


@dataclass
class ScopedTask:
    """Task with serialized selection context"""
    id: str
    name: str
    description: str = ""
    selection: Optional[Selection] = None
    operation: str = ""  # Operation to perform
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, running, completed, failed
    result: Any = None
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "selection": self.selection.to_dict() if self.selection else None,
            "operation": self.operation,
            "parameters": self.parameters,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ScopedTask':
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            selection=Selection.from_dict(data["selection"]) if data.get("selection") else None,
            operation=data.get("operation", ""),
            parameters=data.get("parameters", {}),
            status=data.get("status", "pending"),
            result=data.get("result"),
            error=data.get("error", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
            completed_at=data.get("completed_at", "")
        )


class SelectionManager(QObject):
    """Singleton manager for selection state"""
    
    # Signals
    selection_changed = pyqtSignal(object)  # Selection object
    track_selected = pyqtSignal(str, bool)  # track_id, selected
    clip_selected = pyqtSignal(str, bool)  # clip_id, selected
    time_range_changed = pyqtSignal(float, float)  # start, end
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self._initialized = True
        
        self._current_selection = Selection()
        self._selection_history: List[Selection] = []
        self._max_history = 50
        self._listeners: List[Callable] = []
        self._ui_state: Dict[str, Any] = {
            "selection_visible": True,
            "highlight_color": "#4a9eff",
            "show_time_range": True
        }
    
    def get_selection(self) -> Selection:
        """Get current selection"""
        return self._current_selection
    
    def set_selection(self, selection: Selection, add_to_history: bool = True):
        """Set current selection"""
        if add_to_history:
            self._add_to_history(self._current_selection)
        
        self._current_selection = selection
        self._current_selection.selection_type = selection.get_type()
        self.selection_changed.emit(selection)
    
    def select_tracks(self, track_ids: List[str], extend: bool = False):
        """Select tracks"""
        if extend:
            new_track_ids = self._current_selection.track_ids | set(track_ids)
        else:
            new_track_ids = set(track_ids)
        
        selection = Selection(
            track_ids=new_track_ids,
            time_range=self._current_selection.time_range,
            clip_ids=self._current_selection.clip_ids if extend else set()
        )
        self.set_selection(selection)
        
        for tid in track_ids:
            self.track_selected.emit(tid, True)
    
    def deselect_tracks(self, track_ids: List[str]):
        """Deselect tracks"""
        new_track_ids = self._current_selection.track_ids - set(track_ids)
        
        selection = Selection(
            track_ids=new_track_ids,
            time_range=self._current_selection.time_range,
            clip_ids=self._current_selection.clip_ids
        )
        self.set_selection(selection)
        
        for tid in track_ids:
            self.track_selected.emit(tid, False)
    
    def select_clips(self, clip_ids: List[str], extend: bool = False):
        """Select clips"""
        if extend:
            new_clip_ids = self._current_selection.clip_ids | set(clip_ids)
        else:
            new_clip_ids = set(clip_ids)
        
        selection = Selection(
            track_ids=self._current_selection.track_ids if extend else set(),
            time_range=self._current_selection.time_range,
            clip_ids=new_clip_ids
        )
        self.set_selection(selection)
        
        for cid in clip_ids:
            self.clip_selected.emit(cid, True)
    
    def deselect_clips(self, clip_ids: List[str]):
        """Deselect clips"""
        new_clip_ids = self._current_selection.clip_ids - set(clip_ids)
        
        selection = Selection(
            track_ids=self._current_selection.track_ids,
            time_range=self._current_selection.time_range,
            clip_ids=new_clip_ids
        )
        self.set_selection(selection)
        
        for cid in clip_ids:
            self.clip_selected.emit(cid, False)
    
    def set_time_range(self, start_beat: float, end_beat: float, 
                       start_seconds: float = 0.0, end_seconds: float = 0.0):
        """Set time range selection"""
        time_range = TimeRange(
            start_beat=start_beat,
            end_beat=end_beat,
            start_time_seconds=start_seconds,
            end_time_seconds=end_seconds
        )
        
        selection = Selection(
            track_ids=self._current_selection.track_ids,
            time_range=time_range,
            clip_ids=self._current_selection.clip_ids
        )
        self.set_selection(selection)
        self.time_range_changed.emit(start_beat, end_beat)
    
    def clear_selection(self):
        """Clear all selection"""
        self._add_to_history(self._current_selection)
        self._current_selection = Selection()
        self.selection_changed.emit(self._current_selection)
    
    def clear_time_range(self):
        """Clear time range selection"""
        selection = Selection(
            track_ids=self._current_selection.track_ids,
            time_range=None,
            clip_ids=self._current_selection.clip_ids
        )
        self.set_selection(selection)
    
    def _add_to_history(self, selection: Selection):
        """Add selection to history"""
        self._selection_history.append(selection)
        if len(self._selection_history) > self._max_history:
            self._selection_history.pop(0)
    
    def undo_selection(self) -> bool:
        """Undo to previous selection"""
        if not self._selection_history:
            return False
        
        previous = self._selection_history.pop()
        self._current_selection = previous
        self.selection_changed.emit(previous)
        return True
    
    def get_selection_bounds(self) -> Optional[tuple]:
        """Get selection bounds in beats"""
        if self._current_selection.time_range:
            tr = self._current_selection.time_range
            return (tr.start_beat, tr.end_beat)
        return None
    
    def get_selected_track_count(self) -> int:
        return len(self._current_selection.track_ids)
    
    def get_selected_clip_count(self) -> int:
        return len(self._current_selection.clip_ids)
    
    def create_scoped_task(self, task_id: str, name: str, 
                         operation: str, parameters: Dict = None) -> ScopedTask:
        """Create task with current selection"""
        return ScopedTask(
            id=task_id,
            name=name,
            selection=self._current_selection,
            operation=operation,
            parameters=parameters or {}
        )
    
    def set_ui_state(self, key: str, value: Any):
        """Set UI state value"""
        self._ui_state[key] = value
    
    def get_ui_state(self, key: str, default: Any = None) -> Any:
        """Get UI state value"""
        return self._ui_state.get(key, default)
    
    def is_track_selected(self, track_id: str) -> bool:
        return track_id in self._current_selection.track_ids
    
    def is_clip_selected(self, clip_id: str) -> bool:
        return clip_id in self._current_selection.clip_ids
