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
            'settings': {
                'sample_rate': 44100,
                'bit_depth': 16,
                'channels': 2
            }
        }
        
        self.current_project = project
        return project
        
    def save_project(self, file_path: str, project_data: Dict) -> bool:
        """Save project to file"""
        try:
            # Update metadata
            project_data['modified_at'] = datetime.now().isoformat()
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Save main project file
            with open(file_path, 'w') as f:
                json.dump(project_data, f, indent=2)
                
            # Save backup
            self._create_backup(file_path)
            
            return True
            
        except Exception as e:
            print(f"Error saving project: {e}")
            return False
            
    def load_project(self, file_path: str) -> Dict:
        """Load project from file"""
        with open(file_path, 'r') as f:
            project = json.load(f)
            
        self.current_project = project
        return project
        
    def _create_backup(self, file_path: str):
        """Create a backup of the project"""
        backup_dir = os.path.join(os.path.dirname(file_path), ".backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{os.path.basename(file_path)}.{timestamp}.bak"
        backup_path = os.path.join(backup_dir, backup_name)
        
        try:
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
            os.makedirs(autosave_dir, exist_ok=True)
            
            autosave_path = os.path.join(
                autosave_dir,
                f"{os.path.basename(file_path)}.autosave"
            )
            
            with open(autosave_path, 'w') as f:
                json.dump(project_data, f, indent=2)
                
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
