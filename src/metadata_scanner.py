"""
Metadata Scanner - Copyright safeguard for v1.1 Architecture
TagLib integration for metadata reading and tiered response system
"""

import os
import json
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum
from PyQt6.QtCore import QObject, pyqtSignal


class CopyrightTier(Enum):
    """Copyright risk tiers"""
    GREEN = "green"  # Independent / Safe
    YELLOW = "yellow"  # Caution - Verify rights
    RED = "red"  # Major label - High risk
    UNKNOWN = "unknown"  # Cannot determine


@dataclass
class MetadataScanResult:
    """Result of metadata scan"""
    file_path: str = ""
    tier: CopyrightTier = CopyrightTier.UNKNOWN
    confidence: float = 0.0
    matched_labels: List[str] = field(default_factory=list)
    publisher: str = ""
    copyright_holder: str = ""
    artist: str = ""
    album: str = ""
    title: str = ""
    year: str = ""
    label: str = ""
    comments: str = ""
    warnings: List[str] = field(default_factory=list)
    scanned_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return {
            "file_path": self.file_path,
            "tier": self.tier.value,
            "confidence": self.confidence,
            "matched_labels": self.matched_labels,
            "publisher": self.publisher,
            "copyright_holder": self.copyright_holder,
            "artist": self.artist,
            "album": self.album,
            "title": self.title,
            "year": self.year,
            "label": self.label,
            "comments": self.comments,
            "warnings": self.warnings,
            "scanned_at": self.scanned_at
        }


class MetadataScanner(QObject):
    """Copyright safeguard using metadata analysis"""
    
    # Signals
    scan_complete = pyqtSignal(str, object)  # file_path, MetadataScanResult
    scan_error = pyqtSignal(str, str)  # file_path, error
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, labels_file: str = None):
        if self._initialized:
            return
        super().__init__()
        self._initialized = True
        
        self._labels_data: Dict = {}
        self._major_labels: List[Dict] = []
        self._keywords: Dict[str, List[str]] = {}
        
        # Load labels database
        if labels_file is None:
            labels_file = os.path.join(
                os.path.dirname(__file__), 
                "..", "resources", "major_labels.json"
            )
        
        self._load_labels(labels_file)
    
    def _load_labels(self, labels_file: str):
        """Load major labels database"""
        try:
            if os.path.exists(labels_file):
                with open(labels_file, 'r', encoding='utf-8') as f:
                    self._labels_data = json.load(f)
                    self._major_labels = self._labels_data.get("major_labels", [])
                    self._keywords = self._labels_data.get("keywords", {})
            else:
                # Fallback to built-in minimal list
                self._major_labels = [
                    {"name": "Universal Music Group", "aliases": ["UMG", "Universal"], "tier": "red", "confidence": 0.95},
                    {"name": "Sony Music", "aliases": ["Sony", "Columbia", "RCA"], "tier": "red", "confidence": 0.95},
                    {"name": "Warner Music", "aliases": ["Warner", "Atlantic"], "tier": "red", "confidence": 0.95},
                ]
                self._keywords = {
                    "red": ["sony", "universal", "warner", "emi", "columbia", "rca"],
                    "yellow": ["concord", "sub pop", "matador"],
                    "green": ["distrokid", "cd baby", "tunecore"]
                }
        except Exception as e:
            print(f"Error loading labels file: {e}")
    
    def scan_file(self, file_path: str) -> MetadataScanResult:
        """Scan audio file for copyright metadata"""
        result = MetadataScanResult(file_path=file_path)
        
        try:
            # Try to read metadata using available libraries
            metadata = self._read_metadata(file_path)
            
            result.artist = metadata.get("artist", "")
            result.album = metadata.get("album", "")
            result.title = metadata.get("title", "")
            result.year = metadata.get("date", "")
            result.label = metadata.get("label", "")
            result.publisher = metadata.get("publisher", "")
            result.copyright_holder = metadata.get("copyright", "")
            result.comments = metadata.get("comment", "")
            
            # Analyze for copyright risk
            result = self._analyze_copyright_risk(result)
            
            self.scan_complete.emit(file_path, result)
            return result
            
        except Exception as e:
            result.warnings.append(f"Scan error: {str(e)}")
            self.scan_error.emit(file_path, str(e))
            return result
    
    def _read_metadata(self, file_path: str) -> Dict:
        """Read metadata from audio file"""
        metadata = {}
        
        # Try mutagen first (most common)
        try:
            from mutagen import File
            from mutagen.mp3 import MP3
            from mutagen.flac import FLAC
            from mutagen.wavpack import WavPack
            
            audio = File(file_path)
            if audio:
                # Extract common tags
                if hasattr(audio, 'tags') and audio.tags:
                    tags = audio.tags
                    metadata["artist"] = self._get_tag(tags, ["TPE1", "ARTIST", "Author"])
                    metadata["album"] = self._get_tag(tags, ["TALB", "ALBUM", "ALBUMTITLE"])
                    metadata["title"] = self._get_tag(tags, ["TIT2", "TITLE", "Title"])
                    metadata["date"] = self._get_tag(tags, ["TDRC", "DATE", "Year", "YEAR"])
                    metadata["label"] = self._get_tag(tags, ["TPUB", "LABEL", "Publisher", "PUBLISHER"])
                    metadata["publisher"] = self._get_tag(tags, ["TPUB", "PUBLISHER", "Publisher"])
                    metadata["copyright"] = self._get_tag(tags, ["TCOP", "COPYRIGHT", "Copyright"])
                    metadata["comment"] = self._get_tag(tags, ["COMM", "COMMENT", "Comment"])
                
                # Get technical metadata
                if hasattr(audio, 'info'):
                    metadata["duration"] = getattr(audio.info, 'length', 0)
                    metadata["bitrate"] = getattr(audio.info, 'bitrate', 0)
                    metadata["sample_rate"] = getattr(audio.info, 'sample_rate', 0)
        
        except ImportError:
            # Try tinytag as fallback
            try:
                from tinytag import TinyTag
                tag = TinyTag.get(file_path)
                metadata = {
                    "artist": tag.artist or "",
                    "album": tag.album or "",
                    "title": tag.title or "",
                    "date": str(tag.year) if tag.year else "",
                    "label": "",
                    "publisher": "",
                    "copyright": "",
                    "comment": tag.comment or ""
                }
            except ImportError:
                pass
        
        return metadata
    
    def _get_tag(self, tags, possible_keys: List[str]) -> str:
        """Get tag value from multiple possible keys"""
        for key in possible_keys:
            if key in tags:
                value = tags[key]
                if isinstance(value, list):
                    value = value[0]
                if hasattr(value, 'text'):
                    value = value.text[0] if value.text else ""
                return str(value) if value else ""
        return ""
    
    def _analyze_copyright_risk(self, result: MetadataScanResult) -> MetadataScanResult:
        """Analyze metadata for copyright risk"""
        text_to_check = " ".join([
            result.artist,
            result.album,
            result.title,
            result.label,
            result.publisher,
            result.copyright_holder,
            result.comments
        ]).lower()
        
        # Check against major labels
        matched_labels = []
        highest_tier = CopyrightTier.GREEN
        confidence = 0.0
        
        for label in self._major_labels:
            label_name = label["name"].lower()
            aliases = [a.lower() for a in label.get("aliases", [])]
            
            # Check if label name or aliases appear in metadata
            if label_name in text_to_check:
                matched_labels.append(label["name"])
                tier = CopyrightTier(label["tier"])
                if self._tier_rank(tier) > self._tier_rank(highest_tier):
                    highest_tier = tier
                confidence = max(confidence, label.get("confidence", 0.5))
            else:
                for alias in aliases:
                    if alias in text_to_check:
                        matched_labels.append(f"{label['name']} (via {alias})")
                        tier = CopyrightTier(label["tier"])
                        if self._tier_rank(tier) > self._tier_rank(highest_tier):
                            highest_tier = tier
                        confidence = max(confidence, label.get("confidence", 0.5) * 0.8)
                        break
        
        # Check keywords if no direct match
        if not matched_labels:
            for tier_name, keywords in self._keywords.items():
                for keyword in keywords:
                    if keyword.lower() in text_to_check:
                        matched_labels.append(f"Keyword match: {keyword}")
                        tier = CopyrightTier(tier_name)
                        if self._tier_rank(tier) > self._tier_rank(highest_tier):
                            highest_tier = tier
                        confidence = max(confidence, 0.6)
        
        result.tier = highest_tier
        result.confidence = confidence if matched_labels else 0.0
        result.matched_labels = matched_labels
        
        # Add warnings
        if result.tier == CopyrightTier.RED:
            result.warnings.append("Major label content detected - High copyright risk")
        elif result.tier == CopyrightTier.YELLOW:
            result.warnings.append("Potential rights holder detected - Verify usage rights")
        
        return result
    
    def _tier_rank(self, tier: CopyrightTier) -> int:
        """Get numeric rank for tier comparison"""
        ranks = {
            CopyrightTier.GREEN: 0,
            CopyrightTier.YELLOW: 1,
            CopyrightTier.RED: 2,
            CopyrightTier.UNKNOWN: -1
        }
        return ranks.get(tier, -1)
    
    def can_import_safely(self, file_path: str) -> Tuple[bool, str]:
        """Quick check if file can be safely imported"""
        result = self.scan_file(file_path)
        
        if result.tier == CopyrightTier.RED:
            return False, f"High copyright risk: {', '.join(result.matched_labels)}"
        elif result.tier == CopyrightTier.YELLOW:
            return True, f"Caution: {', '.join(result.matched_labels)} - Verify rights before use"
        else:
            return True, "No copyright concerns detected"
    
    def get_tier_description(self, tier: CopyrightTier) -> str:
        """Get human-readable tier description"""
        descriptions = {
            CopyrightTier.GREEN: "Independent / Safe to use",
            CopyrightTier.YELLOW: "Caution - Verify rights before use",
            CopyrightTier.RED: "Major label content - High copyright risk",
            CopyrightTier.UNKNOWN: "Unable to determine copyright status"
        }
        return descriptions.get(tier, "Unknown")
    
    def get_tier_color(self, tier: CopyrightTier) -> str:
        """Get color code for tier"""
        colors = {
            CopyrightTier.GREEN: "#4caf50",
            CopyrightTier.YELLOW: "#ff9800",
            CopyrightTier.RED: "#f44336",
            CopyrightTier.UNKNOWN: "#9e9e9e"
        }
        return colors.get(tier, "#9e9e9e")
