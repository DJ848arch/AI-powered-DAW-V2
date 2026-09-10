"""
Project Management with JSON Serialization
Handles project save/load operations
"""

import os
import json
import shutil
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime


class ProjectManager:
    """Manages DAW projects"""
    
    PROJECT_EXTENSION = ".daw"
    AUTOSAVE_DIR = ".autosave"
    
    def __init__(self, projects_dir: str = None):
        """Initialize project manager"""
        self.projects_dir = projects_dir or os.path.expanduser("~/.aria/projects")
        self.current_project = None
        self.autosave_enabled = True
        
        # Ensure projects directory exists
        os.makedirs(self.projects_dir, exist_ok=True)
        
    def new_project(self, name: str = "Untitled Project") -> Dict:
        """Create a new project"""
        project = {
            'version': '1.0',
            'name': name,
            'created_at': datetime.now().isoformat(),
            'modified_at': datetime.now().isoformat(),
            'timeline': {
                'tracks': {},
                'clips': {},
                'zoom_level': 1.0,
                'bpm': 120
            },
            'transport': {
                'bpm': 120,
                'beats_per_bar': 4,
                'beat_unit': 4,
                'metronome_active': False,
                'position': 0.0
            },
            'tracks': {},
            'clips': {},
            'midi_clips': {},
            'track_outputs': {},
            'buses': [],
            'settings': {
                'sample_rate': 44100,
                'bit_depth': 16,
                'channels': 2
            }
        }
        
        self.current_project = project
        return project

    def new_track(self, track_id, name="New Track", instrument="piano") -> Dict:
        """Create a persisted track record. instrument is additive."""
        return {
            "id": track_id,
            "name": name,
            "instrument": instrument,
            "clips": [],
            "muted": False,
            "solo": False,
        }

    def ensure_track_instrument(self, track: Dict, default: str = "piano") -> Dict:
        """Set instrument on a track dict if missing (additive)."""
        if "instrument" not in track:
            track["instrument"] = default
        return track

    def _atomic_write_json(self, file_path, data):
        """Write JSON atomically via a sibling temp file, then os.replace."""
        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        tmp_path = file_path + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, file_path)

            # Durable directory entry on POSIX (best-effort).
            dir_to_sync = parent if parent else "."
            try:
                flags = os.O_RDONLY
                if hasattr(os, "O_DIRECTORY"):
                    flags |= os.O_DIRECTORY
                dir_fd = os.open(dir_to_sync, flags)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        
    def _normalize_track_outputs(self, mapping) -> Dict:
        """Normalize track_outputs for JSON: string keys, int or bus-name dests.

        Missing/None/''/'master' dests are omitted — a missing key means master.
        Int dests stay int. Other non-empty strings are kept as bus names
        (e.g. "drum"). Numpy/int-like keys and dests are coerced to Python str/int.
        """
        if not mapping or not isinstance(mapping, dict):
            return {}

        out = {}
        for key, dest in mapping.items():
            try:
                if isinstance(key, bool):
                    continue
                src_str = str(int(key))
            except (TypeError, ValueError):
                continue

            if dest is None:
                continue
            if isinstance(dest, bool):
                continue
            if isinstance(dest, str):
                stripped = dest.strip()
                if stripped == "" or stripped.lower() == "master":
                    continue
                if stripped.lstrip("-").isdigit():
                    out[src_str] = int(stripped)
                else:
                    out[src_str] = stripped
            else:
                try:
                    dest_id = int(dest)
                except (TypeError, ValueError):
                    continue
                out[src_str] = dest_id
        return out

    def _normalize_buses(self, names) -> List:
        """Sorted unique non-empty bus names, excluding 'master' (case-insensitive)."""
        if not names:
            return []
        if isinstance(names, str):
            names = [names]
        try:
            items = list(names)
        except TypeError:
            return []

        seen = set()
        out = []
        for name in items:
            if not isinstance(name, str):
                continue
            stripped = name.strip()
            if not stripped or stripped.lower() == "master":
                continue
            if stripped in seen:
                continue
            seen.add(stripped)
            out.append(stripped)
        return sorted(out)

    def _collect_buses(self, engine) -> List:
        """Normalized bus names from a live engine (or [])."""
        if engine is None:
            return []
        try:
            names = None
            if hasattr(engine, "list_buses"):
                names = engine.list_buses()
            if not names and hasattr(engine, "get_buses"):
                names = engine.get_buses()
        except Exception:
            return []
        return self._normalize_buses(names)

    def _apply_buses(self, engine, names):
        """Register named buses on a live engine. Missing/None/empty → no buses."""
        if engine is None:
            return
        if not names:
            return
        for name in self._normalize_buses(names):
            try:
                engine.add_bus(name)
            except (ValueError, TypeError):
                continue

    def _collect_track_outputs(self, engine) -> Dict:
        """Normalized track_outputs from a live engine (or {})."""
        if engine is None:
            return {}
        try:
            state = engine.get_state() or {}
        except Exception:
            return {}
        return self._normalize_track_outputs(state.get("track_outputs") or {})

    def _apply_track_outputs(self, engine, mapping):
        """Restore buses from current_project, then reapply dests. Invalid dests skipped."""
        if engine is None:
            return
        project = self.current_project or {}
        self._apply_buses(engine, project.get("buses"))
        normalized = self._normalize_track_outputs(mapping)
        for src_str, dest in normalized.items():
            try:
                src = int(src_str)
            except (TypeError, ValueError):
                continue
            try:
                engine.set_track_output(src, dest)
            except (ValueError, TypeError):
                continue

    def save_project(self, file_path: str, project_data: Dict, engine=None) -> bool:
        """Save project to file. Optional engine overlays track_outputs and buses."""
        try:
            # Update metadata
            project_data['modified_at'] = datetime.now().isoformat()

            if engine is not None:
                project_data['track_outputs'] = self._collect_track_outputs(engine)
                project_data['buses'] = self._collect_buses(engine)
            else:
                if 'track_outputs' in project_data:
                    project_data['track_outputs'] = self._normalize_track_outputs(
                        project_data.get('track_outputs')
                    )
                if 'buses' in project_data:
                    project_data['buses'] = self._normalize_buses(
                        project_data.get('buses')
                    )

            # Backup the existing good file before replacing it
            if os.path.exists(file_path):
                self._create_backup(file_path)

            self._atomic_write_json(file_path, project_data)
            return True
            
        except Exception as e:
            print(f"Error saving project: {e}")
            return False
            
    def load_project(self, file_path: str, engine=None) -> Dict:
        """Load project from file. Optional engine restores track_outputs."""
        with open(file_path, 'r') as f:
            project = json.load(f)

        project = self.migrate_project(project)

        if not self.validate_project(project):
            raise ValueError(
                "Invalid project file: missing required keys "
                "(version, timeline, transport)"
            )

        self.current_project = project

        if engine is not None:
            self._apply_buses(engine, project.get('buses'))
            self._apply_track_outputs(engine, project.get('track_outputs') or {})

        return project
        
    def _create_backup(self, file_path: str):
        """Create a backup of the project"""
        if not os.path.exists(file_path):
            return

        try:
            backup_dir = os.path.join(os.path.dirname(file_path), ".backups")
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{os.path.basename(file_path)}.{timestamp}.bak"
            backup_path = os.path.join(backup_dir, backup_name)
            
            shutil.copy2(file_path, backup_path)
            
            # Keep only last 10 backups
            backups = sorted([
                f for f in os.listdir(backup_dir)
                if f.startswith(os.path.basename(file_path))
            ])
            
            while len(backups) > 10:
                old_backup = os.path.join(backup_dir, backups.pop(0))
                os.remove(old_backup)
                
        except Exception as e:
            print(f"Error creating backup: {e}")
            
    def autosave(self, file_path: str, project_data: Dict):
        """Auto-save project"""
        if not self.autosave_enabled:
            return
            
        try:
            autosave_dir = os.path.join(os.path.dirname(file_path), self.AUTOSAVE_DIR)
            autosave_path = os.path.join(
                autosave_dir,
                f"{os.path.basename(file_path)}.autosave"
            )

            self._atomic_write_json(autosave_path, project_data)
                
        except Exception as e:
            print(f"Error during autosave: {e}")
            
    def get_recent_projects(self, limit: int = 10) -> List[Dict]:
        """Get list of recent projects"""
        recent_file = os.path.join(self.projects_dir, "recent_projects.json")
        
        if os.path.exists(recent_file):
            with open(recent_file, 'r') as f:
                recent = json.load(f)
                return recent[:limit]
                
        return []
        
    def add_to_recent(self, file_path: str):
        """Add project to recent list"""
        recent_file = os.path.join(self.projects_dir, "recent_projects.json")
        
        recent = self.get_recent_projects(limit=100)
        
        # Remove if already exists
        recent = [p for p in recent if p['path'] != file_path]
        
        # Add to front
        recent.insert(0, {
            'path': file_path,
            'name': os.path.basename(file_path),
            'last_opened': datetime.now().isoformat()
        })
        
        # Keep only last 20
        recent = recent[:20]
        
        with open(recent_file, 'w') as f:
            json.dump(recent, f, indent=2)
            
    def export_project(self, file_path: str, format: str = 'json') -> bool:
        """Export project to different format"""
        try:
            if format == 'json':
                # Already JSON, just copy
                return True
            elif format == 'xml':
                # Convert to XML (placeholder)
                return True
            else:
                return False
                
        except Exception as e:
            print(f"Error exporting project: {e}")
            return False
            
    def get_project_info(self, file_path: str) -> Optional[Dict]:
        """Get project metadata without loading full project"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            return {
                'name': data.get('name', 'Unknown'),
                'created_at': data.get('created_at', 'Unknown'),
                'modified_at': data.get('modified_at', 'Unknown'),
                'version': data.get('version', 'Unknown'),
                'track_count': len(data.get('tracks', {})),
                'clip_count': len(data.get('clips', {}))
            }
            
        except Exception as e:
            print(f"Error reading project info: {e}")
            return None
            
    def validate_project(self, project_data: Dict) -> bool:
        """Validate project data structure"""
        required_keys = ['version', 'timeline', 'transport']
        
        for key in required_keys:
            if key not in project_data:
                return False
                
        return True
        
    def migrate_project(self, project_data: Dict) -> Dict:
        """Migrate old project format to current"""
        version = project_data.get('version', '1.0')
        
        # Add migration logic here as versions change
        if version == '1.0':
            # Current version, no migration needed
            pass
            
        return project_data
