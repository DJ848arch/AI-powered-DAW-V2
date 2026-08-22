"""
Lock Manager - Locked content enforcement for v1.1 Architecture
Document layer enforcement and transparency panel logging
"""

from typing import List, Set, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import re
from PyQt6.QtCore import QObject, pyqtSignal


class LockLevel(Enum):
    """Lock levels for content protection"""
    NONE = "none"
    WARNING = "warning"  # Can override with confirmation
    PROTECTED = "protected"  # Requires explicit unlock
    LOCKED = "locked"  # Cannot be modified


@dataclass
class LockEntry:
    """Single lock entry"""
    path: str  # JSON Pointer path
    level: LockLevel
    reason: str = ""
    locked_by: str = ""  # Agent ID or user
    locked_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: str = ""  # Optional expiration
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.now().isoformat() > self.expires_at
    
    def to_dict(self) -> Dict:
        return {
            "path": self.path,
            "level": self.level.value,
            "reason": self.reason,
            "locked_by": self.locked_by,
            "locked_at": self.locked_at,
            "expires_at": self.expires_at,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'LockEntry':
        return cls(
            path=data["path"],
            level=LockLevel(data.get("level", "none")),
            reason=data.get("reason", ""),
            locked_by=data.get("locked_by", ""),
            locked_at=data.get("locked_at", datetime.now().isoformat()),
            expires_at=data.get("expires_at", ""),
            metadata=data.get("metadata", {})
        )


@dataclass
class TransparencyLogEntry:
    """Log entry for transparency panel"""
    timestamp: str
    action: str
    agent_id: str
    paths_affected: List[str]
    lock_violations: List[str]
    user_override: bool
    details: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "agent_id": self.agent_id,
            "paths_affected": self.paths_affected,
            "lock_violations": self.lock_violations,
            "user_override": self.user_override,
            "details": self.details
        }


class LockManager(QObject):
    """Document layer enforcement - final gatekeeper for modifications"""
    
    # Signals
    lock_violation = pyqtSignal(str, str, str)  # path, operation, reason
    lock_applied = pyqtSignal(str, str)  # path, level
    lock_removed = pyqtSignal(str)  # path
    transparency_log_entry = pyqtSignal(object)  # TransparencyLogEntry
    
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
        
        self._locks: Dict[str, LockEntry] = {}
        self._transparency_log: List[TransparencyLogEntry] = []
        self._max_log_entries = 1000
        self._enforcement_enabled = True
        self._auto_lock_protected = True  # Auto-lock protected content
        
    def is_locked(self, path: str) -> bool:
        """Check if path is locked"""
        entry = self._locks.get(path)
        if not entry:
            return False
        if entry.is_expired():
            del self._locks[path]
            return False
        return entry.level == LockLevel.LOCKED
    
    def is_protected(self, path: str) -> bool:
        """Check if path is protected"""
        entry = self._locks.get(path)
        if not entry:
            return False
        if entry.is_expired():
            del self._locks[path]
            return False
        return entry.level in [LockLevel.PROTECTED, LockLevel.LOCKED]
    
    def get_lock_level(self, path: str) -> LockLevel:
        """Get lock level for path"""
        entry = self._locks.get(path)
        if not entry or entry.is_expired():
            return LockLevel.NONE
        return entry.level
    
    def get_lock_reason(self, path: str) -> str:
        """Get lock reason for path"""
        entry = self._locks.get(path)
        if entry and not entry.is_expired():
            return entry.reason
        return ""
    
    def apply_lock(self, path: str, level: LockLevel, reason: str = "",
                   locked_by: str = "", expires_at: str = "",
                   metadata: Dict = None):
        """Apply lock to path"""
        entry = LockEntry(
            path=path,
            level=level,
            reason=reason,
            locked_by=locked_by,
            expires_at=expires_at,
            metadata=metadata or {}
        )
        self._locks[path] = entry
        self.lock_applied.emit(path, level.value)
    
    def remove_lock(self, path: str, unlocked_by: str = "") -> bool:
        """Remove lock from path"""
        if path in self._locks:
            del self._locks[path]
            self.lock_removed.emit(path)
            return True
        return False
    
    def remove_all_locks(self, pattern: str = None):
        """Remove all locks, optionally matching pattern"""
        if pattern:
            paths_to_remove = [p for p in self._locks.keys() if re.match(pattern, p)]
            for path in paths_to_remove:
                del self._locks[path]
                self.lock_removed.emit(path)
        else:
            self._locks.clear()
    
    def validate_transaction(self, paths: List[str], 
                            agent_id: str = "") -> tuple:
        """
        Validate transaction against locked paths
        Returns: (is_valid, violations, requires_override)
        """
        if not self._enforcement_enabled:
            return True, [], False
        
        violations = []
        requires_override = False
        
        for path in paths:
            level = self.get_lock_level(path)
            
            if level == LockLevel.LOCKED:
                violations.append({
                    "path": path,
                    "level": level.value,
                    "reason": self.get_lock_reason(path),
                    "blocking": True
                })
            elif level == LockLevel.PROTECTED:
                violations.append({
                    "path": path,
                    "level": level.value,
                    "reason": self.get_lock_reason(path),
                    "blocking": False
                })
                requires_override = True
            elif level == LockLevel.WARNING:
                violations.append({
                    "path": path,
                    "level": level.value,
                    "reason": self.get_lock_reason(path),
                    "blocking": False
                })
        
        is_valid = not any(v["blocking"] for v in violations)
        return is_valid, violations, requires_override
    
    def check_clip_locked(self, clip_id: str) -> bool:
        """Check if clip is locked"""
        return self.is_locked(f"/clips/{clip_id}")
    
    def check_track_locked(self, track_id: str) -> bool:
        """Check if track is locked"""
        return self.is_locked(f"/tracks/{track_id}")
    
    def lock_clip(self, clip_id: str, level: LockLevel = LockLevel.LOCKED,
                  reason: str = "", locked_by: str = ""):
        """Lock a clip"""
        self.apply_lock(f"/clips/{clip_id}", level, reason, locked_by)
    
    def lock_track(self, track_id: str, level: LockLevel = LockLevel.LOCKED,
                   reason: str = "", locked_by: str = ""):
        """Lock a track"""
        self.apply_lock(f"/tracks/{track_id}", level, reason, locked_by)
    
    def unlock_clip(self, clip_id: str, unlocked_by: str = "") -> bool:
        """Unlock a clip"""
        return self.remove_lock(f"/clips/{clip_id}", unlocked_by)
    
    def unlock_track(self, track_id: str, unlocked_by: str = "") -> bool:
        """Unlock a track"""
        return self.remove_lock(f"/tracks/{track_id}", unlocked_by)
    
    def log_transparency_event(self, action: str, agent_id: str,
                               paths_affected: List[str],
                               lock_violations: List[str],
                               user_override: bool,
                               details: Dict = None):
        """Log event to transparency panel"""
        entry = TransparencyLogEntry(
            timestamp=datetime.now().isoformat(),
            action=action,
            agent_id=agent_id,
            paths_affected=paths_affected,
            lock_violations=lock_violations,
            user_override=user_override,
            details=details or {}
        )
        
        self._transparency_log.append(entry)
        
        # Limit log size
        if len(self._transparency_log) > self._max_log_entries:
            self._transparency_log.pop(0)
        
        self.transparency_log_entry.emit(entry)
    
    def get_transparency_log(self, limit: int = None,
                            agent_filter: str = None) -> List[TransparencyLogEntry]:
        """Get transparency log entries"""
        logs = self._transparency_log
        
        if agent_filter:
            logs = [l for l in logs if l.agent_id == agent_filter]
        
        if limit:
            logs = logs[-limit:]
        
        return logs
    
    def get_active_locks(self) -> List[LockEntry]:
        """Get all active locks"""
        active = []
        expired = []
        
        for path, entry in self._locks.items():
            if entry.is_expired():
                expired.append(path)
            else:
                active.append(entry)
        
        # Clean up expired
        for path in expired:
            del self._locks[path]
        
        return active
    
    def get_locks_by_pattern(self, pattern: str) -> List[LockEntry]:
        """Get locks matching pattern"""
        return [entry for path, entry in self._locks.items() 
                if re.match(pattern, path)]
    
    def set_enforcement_enabled(self, enabled: bool):
        """Enable/disable lock enforcement"""
        self._enforcement_enabled = enabled
    
    def is_enforcement_enabled(self) -> bool:
        return self._enforcement_enabled
    
    def auto_protect_on_finalize(self, document: Dict):
        """Auto-lock finalized content"""
        if not self._auto_lock_protected:
            return
        
        # Lock all clips marked as finalized
        clips = document.get("clips", {})
        for clip_id, clip_data in clips.items():
            if clip_data.get("finalized", False):
                self.lock_clip(
                    clip_id,
                    LockLevel.PROTECTED,
                    "Clip finalized - protected from accidental changes",
                    "system"
                )
        
        # Lock tracks marked as locked
        tracks = document.get("tracks", {})
        for track_id, track_data in tracks.items():
            if track_data.get("locked", False):
                self.lock_track(
                    track_id,
                    LockLevel.LOCKED,
                    "Track locked by user",
                    "user"
                )
    
    def export_locks(self) -> List[Dict]:
        """Export all locks for save"""
        return [entry.to_dict() for entry in self.get_active_locks()]
    
    def import_locks(self, locks_data: List[Dict]):
        """Import locks from save"""
        for lock_dict in locks_data:
            entry = LockEntry.from_dict(lock_dict)
            if not entry.is_expired():
                self._locks[entry.path] = entry
