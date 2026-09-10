"""
Project Management with JSON Serialization
Handles project save/load operations

Authoritative .daw shape: SCHEMA.md (version 1.1).
Engine owns signal flow; this module persists/restores the graph.
"""

import math
import os
import json
import shutil
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime


class ProjectManager:
    """Manages DAW projects"""
    
    PROJECT_EXTENSION = ".daw"
    AUTOSAVE_DIR = ".autosave"
    SCHEMA_VERSION = "1.1"
    LEGACY_SCHEMA_VERSION = "1.0"
    
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
            'version': self.SCHEMA_VERSION,
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
            'track_sends': {},
            'track_send_levels': {},
            'track_send_modes': {},
            'inserts': {},
            'bus_outputs': {},
            'bus_volumes': {},
            'bus_pans': {},
            'bus_sends': {},
            'bus_send_levels': {},
            'bus_send_modes': {},
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

    def _normalize_send_dest(self, dest):
        """Int track id or bus name. Master / empty / invalid → None."""
        if dest is None or isinstance(dest, bool):
            return None
        if isinstance(dest, str):
            stripped = dest.strip()
            if not stripped or stripped.lower() == "master":
                return None
            if stripped.lstrip("-").isdigit():
                return int(stripped)
            return stripped
        try:
            return int(dest)
        except (TypeError, ValueError):
            return None

    def _normalize_send_level(self, level):
        """Finite non-negative gain, or None if invalid."""
        if isinstance(level, bool):
            return None
        try:
            gain = float(level)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(gain) or gain < 0.0:
            return None
        return gain

    def _normalize_track_sends(self, mapping) -> Dict:
        """JSON sends: string keys, dest list (int track or bus name)."""
        if not mapping or not isinstance(mapping, dict):
            return {}
        out = {}
        for key, dests in mapping.items():
            try:
                if isinstance(key, bool):
                    continue
                src = int(key)
                src_str = str(src)
            except (TypeError, ValueError):
                continue
            if dests is None or isinstance(dests, dict):
                continue
            if isinstance(dests, (str, bytes)) or not hasattr(dests, "__iter__"):
                dests = [dests]
            seen = set()
            kept = []
            for dest in dests:
                dest_norm = self._normalize_send_dest(dest)
                if dest_norm is None or dest_norm == src:
                    continue
                marker = ("t", dest_norm) if isinstance(dest_norm, int) else ("b", dest_norm)
                if marker in seen:
                    continue
                seen.add(marker)
                kept.append(dest_norm)
            if kept:
                out[src_str] = kept
        return out

    def _normalize_track_send_levels(self, mapping) -> Dict:
        """JSON send levels: string keys, dest-key → finite ≥ 0 gain."""
        if not mapping or not isinstance(mapping, dict):
            return {}
        out = {}
        for key, levels in mapping.items():
            try:
                if isinstance(key, bool):
                    continue
                src_str = str(int(key))
            except (TypeError, ValueError):
                continue
            if not levels or not isinstance(levels, dict):
                continue
            kept = {}
            for dest_key, raw in levels.items():
                dest_norm = self._normalize_send_dest(dest_key)
                gain = self._normalize_send_level(raw)
                if dest_norm is None or gain is None:
                    continue
                kept[str(dest_norm)] = gain
            if kept:
                out[src_str] = kept
        return out

    def _channel_key(self, key):
        """Track id as decimal string, or bus name. None if invalid."""
        if isinstance(key, bool):
            return None
        if isinstance(key, str):
            stripped = key.strip()
            if not stripped or stripped.lower() == "master":
                return None
            if stripped.lstrip("-").isdigit():
                return str(int(stripped))
            return stripped
        try:
            return str(int(key))
        except (TypeError, ValueError):
            return None

    def _normalize_inserts(self, mapping) -> Dict:
        """JSON insert slots: string keys (track id or bus name), list of dicts.

        Empty list = identity / dry. Unknown dict keys kept. Non-dict items dropped.
        """
        if not mapping or not isinstance(mapping, dict):
            return {}
        out = {}
        for key, slots in mapping.items():
            src_str = self._channel_key(key)
            if src_str is None:
                continue
            if slots is None:
                out[src_str] = []
                continue
            if not isinstance(slots, list):
                continue
            kept = [dict(slot) for slot in slots if isinstance(slot, dict)]
            out[src_str] = kept
        return out

    def _normalize_send_mode(self, mode):
        if mode is None:
            return "post"
        if not isinstance(mode, str):
            return None
        stripped = mode.strip().lower()
        if stripped in ("pre", "pre-fader", "prefader"):
            return "pre"
        if stripped in ("post", "post-fader", "postfader", ""):
            return "post"
        return None

    def _normalize_send_modes(self, mapping) -> Dict:
        """JSON send modes: string source keys, dest-key → pre|post."""
        if not mapping or not isinstance(mapping, dict):
            return {}
        out = {}
        for key, modes in mapping.items():
            src_str = self._channel_key(key)
            if src_str is None or not modes or not isinstance(modes, dict):
                continue
            kept = {}
            for dest_key, raw in modes.items():
                dest_norm = self._normalize_send_dest(dest_key)
                mode = self._normalize_send_mode(raw)
                if dest_norm is None or mode is None:
                    continue
                kept[str(dest_norm)] = mode
            if kept:
                out[src_str] = kept
        return out

    def _normalize_bus_float_map(self, mapping, lo, hi, default=None) -> Dict:
        if not mapping or not isinstance(mapping, dict):
            return {}
        out = {}
        for key, raw in mapping.items():
            if not isinstance(key, str):
                continue
            name = key.strip()
            if not name or name.lower() == "master":
                continue
            if isinstance(raw, bool):
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            out[name] = max(lo, min(hi, value))
        return out

    def _normalize_bus_outputs(self, mapping) -> Dict:
        """Bus dests: missing/master omitted. Int track or bus name."""
        if not mapping or not isinstance(mapping, dict):
            return {}
        out = {}
        for key, dest in mapping.items():
            if not isinstance(key, str):
                continue
            name = key.strip()
            if not name or name.lower() == "master":
                continue
            dest_norm = self._normalize_send_dest(dest)
            if dest_norm is None or dest_norm == name:
                continue
            out[name] = dest_norm
        return out

    def _normalize_named_sends(self, mapping) -> Dict:
        """Sends keyed by bus name (not track id)."""
        if not mapping or not isinstance(mapping, dict):
            return {}
        out = {}
        for key, dests in mapping.items():
            if not isinstance(key, str):
                continue
            name = key.strip()
            if not name or name.lower() == "master":
                continue
            if dests is None or isinstance(dests, dict):
                continue
            if isinstance(dests, (str, bytes)) or not hasattr(dests, "__iter__"):
                dests = [dests]
            seen = set()
            kept = []
            for dest in dests:
                dest_norm = self._normalize_send_dest(dest)
                if dest_norm is None or dest_norm == name:
                    continue
                marker = ("t", dest_norm) if isinstance(dest_norm, int) else ("b", dest_norm)
                if marker in seen:
                    continue
                seen.add(marker)
                kept.append(dest_norm)
            if kept:
                out[name] = kept
        return out

    def _normalize_named_levels(self, mapping) -> Dict:
        if not mapping or not isinstance(mapping, dict):
            return {}
        out = {}
        for key, levels in mapping.items():
            if not isinstance(key, str):
                continue
            name = key.strip()
            if not name or name.lower() == "master" or not isinstance(levels, dict):
                continue
            kept = {}
            for dest_key, raw in levels.items():
                dest_norm = self._normalize_send_dest(dest_key)
                gain = self._normalize_send_level(raw)
                if dest_norm is None or gain is None:
                    continue
                kept[str(dest_norm)] = gain
            if kept:
                out[name] = kept
        return out

    def _collect_sends(self, engine) -> Tuple[Dict, Dict, Dict]:
        """Normalized track_sends + levels + modes from a live engine."""
        if engine is None:
            return {}, {}, {}
        raw = getattr(engine, "track_sends", None) or {}
        sends = {}
        levels = {}
        modes = {}
        for key, dests in raw.items():
            try:
                if isinstance(key, bool):
                    continue
                src = int(key)
            except (TypeError, ValueError):
                continue
            src_str = str(src)
            if hasattr(engine, "get_sends"):
                try:
                    dests = engine.get_sends(src)
                except Exception:
                    dests = dests
            kept = []
            kept_levels = {}
            kept_modes = {}
            for dest in dests or []:
                dest_norm = self._normalize_send_dest(dest)
                if dest_norm is None or dest_norm == src:
                    continue
                kept.append(dest_norm)
                gain = 1.0
                if hasattr(engine, "get_send_level"):
                    try:
                        gain = float(engine.get_send_level(src, dest_norm))
                    except (ValueError, TypeError):
                        gain = 1.0
                norm_gain = self._normalize_send_level(gain)
                kept_levels[str(dest_norm)] = 1.0 if norm_gain is None else norm_gain
                mode = "post"
                if hasattr(engine, "get_send_mode"):
                    try:
                        mode = engine.get_send_mode(src, dest_norm)
                    except (ValueError, TypeError):
                        mode = "post"
                norm_mode = self._normalize_send_mode(mode)
                if norm_mode:
                    kept_modes[str(dest_norm)] = norm_mode
            if kept:
                sends[src_str] = kept
                levels[src_str] = kept_levels
                if kept_modes:
                    modes[src_str] = kept_modes
        return (
            self._normalize_track_sends(sends),
            self._normalize_track_send_levels(levels),
            self._normalize_send_modes(modes),
        )

    def _collect_inserts(self, engine) -> Dict:
        if engine is None:
            return {}
        raw = getattr(engine, "channel_inserts", None) or {}
        out = {}
        for key, slots in raw.items():
            src_str = self._channel_key(key)
            if src_str is None:
                continue
            if hasattr(engine, "get_inserts"):
                try:
                    slots = engine.get_inserts(key)
                except Exception:
                    slots = slots
            out[src_str] = [dict(s) for s in (slots or []) if isinstance(s, dict)]
        return self._normalize_inserts(out)

    def _collect_bus_mixer(self, engine) -> Dict:
        """Additive bus-channel fields from a live engine."""
        empty = {
            "bus_outputs": {},
            "bus_volumes": {},
            "bus_pans": {},
            "bus_sends": {},
            "bus_send_levels": {},
            "bus_send_modes": {},
        }
        if engine is None:
            return empty
        names = []
        try:
            names = list(engine.list_buses()) if hasattr(engine, "list_buses") else []
        except Exception:
            names = []
        outputs = {}
        volumes = {}
        pans = {}
        sends = {}
        levels = {}
        modes = {}
        for name in names:
            if hasattr(engine, "get_bus_output"):
                try:
                    dest = engine.get_bus_output(name)
                except Exception:
                    dest = "master"
                dest_norm = self._normalize_send_dest(dest)
                if dest_norm is not None:
                    outputs[name] = dest_norm
            if hasattr(engine, "get_bus_volume"):
                try:
                    volumes[name] = float(engine.get_bus_volume(name))
                except Exception:
                    pass
            if hasattr(engine, "get_bus_pan"):
                try:
                    pans[name] = float(engine.get_bus_pan(name))
                except Exception:
                    pass
            dests = []
            if hasattr(engine, "get_sends"):
                try:
                    dests = engine.get_sends(name)
                except Exception:
                    dests = list((getattr(engine, "bus_sends", {}) or {}).get(name) or [])
            kept = []
            kept_levels = {}
            kept_modes = {}
            for dest in dests or []:
                dest_norm = self._normalize_send_dest(dest)
                if dest_norm is None or dest_norm == name:
                    continue
                kept.append(dest_norm)
                gain = 1.0
                if hasattr(engine, "get_send_level"):
                    try:
                        gain = float(engine.get_send_level(name, dest_norm))
                    except (ValueError, TypeError):
                        gain = 1.0
                norm_gain = self._normalize_send_level(gain)
                kept_levels[str(dest_norm)] = 1.0 if norm_gain is None else norm_gain
                mode = "post"
                if hasattr(engine, "get_send_mode"):
                    try:
                        mode = engine.get_send_mode(name, dest_norm)
                    except (ValueError, TypeError):
                        mode = "post"
                norm_mode = self._normalize_send_mode(mode)
                if norm_mode:
                    kept_modes[str(dest_norm)] = norm_mode
            if kept:
                sends[name] = kept
                levels[name] = kept_levels
                if kept_modes:
                    modes[name] = kept_modes
        return {
            "bus_outputs": self._normalize_bus_outputs(outputs),
            "bus_volumes": self._normalize_bus_float_map(volumes, 0.0, 1.0),
            "bus_pans": self._normalize_bus_float_map(pans, -1.0, 1.0),
            "bus_sends": self._normalize_named_sends(sends),
            "bus_send_levels": self._normalize_named_levels(levels),
            "bus_send_modes": self._normalize_send_modes(modes),
        }

    def _ensure_engine_track_live(self, engine, track_id: int):
        """Make a dest track live via public mixer state (no new engine API)."""
        if engine is None or not hasattr(engine, "set_track_volume"):
            return
        try:
            current = engine.get_track_volume(track_id) if hasattr(engine, "get_track_volume") else 1.0
        except Exception:
            current = 1.0
        try:
            engine.set_track_volume(track_id, current)
        except Exception:
            pass

    def _apply_sends(self, engine, sends=None, levels=None, modes=None):
        """Restore extra sends after buses. Invalid dests skipped.

        Track dests are made live with the dest's existing volume (default 1.0)
        so add_send's live-dest rule can succeed without a new engine API.
        """
        if engine is None:
            return
        project = self.current_project or {}
        self._apply_buses(engine, project.get("buses"))
        if sends is None:
            sends = project.get("track_sends")
        if levels is None:
            levels = project.get("track_send_levels")
        if modes is None:
            modes = project.get("track_send_modes")
        normalized = self._normalize_track_sends(sends)
        level_map = self._normalize_track_send_levels(levels)
        mode_map = self._normalize_send_modes(modes)
        for src_str, dests in normalized.items():
            try:
                src = int(src_str)
            except (TypeError, ValueError):
                continue
            src_levels = level_map.get(src_str) or {}
            src_modes = mode_map.get(src_str) or {}
            for dest in dests:
                if isinstance(dest, int):
                    self._ensure_engine_track_live(engine, dest)
                gain = src_levels.get(str(dest), 1.0)
                mode = src_modes.get(str(dest), "post")
                try:
                    engine.add_send(src, dest, gain, mode=mode)
                except TypeError:
                    try:
                        engine.add_send(src, dest, gain)
                    except (ValueError, TypeError):
                        continue
                except (ValueError, TypeError):
                    continue

    def _apply_inserts(self, engine, inserts=None):
        if engine is None or not hasattr(engine, "set_inserts"):
            return
        project = self.current_project or {}
        self._apply_buses(engine, project.get("buses"))
        if inserts is None:
            inserts = project.get("inserts")
        for key, slots in self._normalize_inserts(inserts).items():
            channel = int(key) if key.lstrip("-").isdigit() else key
            try:
                engine.set_inserts(channel, slots)
            except (ValueError, TypeError):
                continue

    def _apply_bus_mixer(self, engine, project=None):
        if engine is None:
            return
        project = project or self.current_project or {}
        self._apply_buses(engine, project.get("buses"))
        for name, dest in self._normalize_bus_outputs(project.get("bus_outputs")).items():
            if isinstance(dest, int):
                self._ensure_engine_track_live(engine, dest)
            if hasattr(engine, "set_bus_output"):
                try:
                    engine.set_bus_output(name, dest)
                except (ValueError, TypeError):
                    continue
        for name, vol in self._normalize_bus_float_map(
            project.get("bus_volumes"), 0.0, 1.0
        ).items():
            if hasattr(engine, "set_bus_volume"):
                try:
                    engine.set_bus_volume(name, vol)
                except (ValueError, TypeError):
                    continue
        for name, pan in self._normalize_bus_float_map(
            project.get("bus_pans"), -1.0, 1.0
        ).items():
            if hasattr(engine, "set_bus_pan"):
                try:
                    engine.set_bus_pan(name, pan)
                except (ValueError, TypeError):
                    continue
        level_map = self._normalize_named_levels(project.get("bus_send_levels"))
        mode_map = self._normalize_send_modes(project.get("bus_send_modes"))
        for name, dests in self._normalize_named_sends(project.get("bus_sends")).items():
            src_levels = level_map.get(name) or {}
            src_modes = mode_map.get(name) or {}
            for dest in dests:
                if isinstance(dest, int):
                    self._ensure_engine_track_live(engine, dest)
                gain = src_levels.get(str(dest), 1.0)
                mode = src_modes.get(str(dest), "post")
                try:
                    engine.add_send(name, dest, gain, mode=mode)
                except TypeError:
                    try:
                        engine.add_send(name, dest, gain)
                    except (ValueError, TypeError):
                        continue
                except (ValueError, TypeError):
                    continue

    def canonicalize_project(self, project_data: Dict) -> Dict:
        """Ensure current schema graph keys. Does not drop unknown keys."""
        if not isinstance(project_data, dict):
            return project_data

        project_data["version"] = self.SCHEMA_VERSION
        project_data["track_outputs"] = self._normalize_track_outputs(
            project_data.get("track_outputs")
        )
        project_data["buses"] = self._normalize_buses(project_data.get("buses"))
        project_data["track_sends"] = self._normalize_track_sends(
            project_data.get("track_sends")
        )
        project_data["track_send_levels"] = self._normalize_track_send_levels(
            project_data.get("track_send_levels")
        )
        project_data["track_send_modes"] = self._normalize_send_modes(
            project_data.get("track_send_modes")
        )
        project_data["inserts"] = self._normalize_inserts(project_data.get("inserts"))
        project_data["bus_outputs"] = self._normalize_bus_outputs(
            project_data.get("bus_outputs")
        )
        project_data["bus_volumes"] = self._normalize_bus_float_map(
            project_data.get("bus_volumes"), 0.0, 1.0
        )
        project_data["bus_pans"] = self._normalize_bus_float_map(
            project_data.get("bus_pans"), -1.0, 1.0
        )
        project_data["bus_sends"] = self._normalize_named_sends(
            project_data.get("bus_sends")
        )
        project_data["bus_send_levels"] = self._normalize_named_levels(
            project_data.get("bus_send_levels")
        )
        project_data["bus_send_modes"] = self._normalize_send_modes(
            project_data.get("bus_send_modes")
        )
        return project_data

    def save_project(self, file_path: str, project_data: Dict, engine=None) -> bool:
        """Save project to file. Optional engine overlays routing graph keys."""
        try:
            # Update metadata
            project_data['modified_at'] = datetime.now().isoformat()

            prior = self.current_project or {}
            if "inserts" not in project_data and prior.get("inserts") is not None:
                project_data["inserts"] = prior.get("inserts")

            if engine is not None:
                project_data['track_outputs'] = self._collect_track_outputs(engine)
                project_data['buses'] = self._collect_buses(engine)
                sends, levels, modes = self._collect_sends(engine)
                project_data['track_sends'] = sends
                project_data['track_send_levels'] = levels
                project_data['track_send_modes'] = modes
                engine_inserts = self._collect_inserts(engine)
                prior_inserts = self._normalize_inserts(project_data.get("inserts"))
                merged = dict(prior_inserts)
                merged.update(engine_inserts)
                project_data['inserts'] = merged
                project_data.update(self._collect_bus_mixer(engine))
            self.canonicalize_project(project_data)

            # Backup the existing good file before replacing it
            if os.path.exists(file_path):
                self._create_backup(file_path)

            self._atomic_write_json(file_path, project_data)
            return True
            
        except Exception as e:
            print(f"Error saving project: {e}")
            return False
            
    def load_project(self, file_path: str, engine=None) -> Dict:
        """Load project from file. Optional engine restores routing graph."""
        with open(file_path, 'r') as f:
            project = json.load(f)

        project = self.migrate_project(project)
        project = self.canonicalize_project(project)

        if not self.validate_project(project):
            raise ValueError(
                "Invalid project file: missing required keys "
                "(version, timeline, transport)"
            )

        self.current_project = project

        if engine is not None:
            self._apply_buses(engine, project.get('buses'))
            self._apply_bus_mixer(engine, project)
            self._apply_track_outputs(engine, project.get('track_outputs') or {})
            self._apply_inserts(engine, project.get('inserts'))
            self._apply_sends(
                engine,
                project.get('track_sends'),
                project.get('track_send_levels'),
                project.get('track_send_modes'),
            )

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

            self.canonicalize_project(project_data)
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
        """Migrate old project format to current (1.0 → 1.1).

        Missing graph keys get M1-safe empties. Unknown keys are kept.
        Version is bumped; canonicalize_project runs on load after this.
        """
        if not isinstance(project_data, dict):
            return project_data

        version = str(project_data.get('version') or self.LEGACY_SCHEMA_VERSION)

        if version in (self.LEGACY_SCHEMA_VERSION, "1"):
            project_data['version'] = self.SCHEMA_VERSION
            project_data.setdefault('track_outputs', {})
            project_data.setdefault('buses', [])
            project_data.setdefault('track_sends', {})
            project_data.setdefault('track_send_levels', {})
            project_data.setdefault('track_send_modes', {})
            project_data.setdefault('inserts', {})
            project_data.setdefault('bus_outputs', {})
            project_data.setdefault('bus_volumes', {})
            project_data.setdefault('bus_pans', {})
            project_data.setdefault('bus_sends', {})
            project_data.setdefault('bus_send_levels', {})
            project_data.setdefault('bus_send_modes', {})

        return project_data
