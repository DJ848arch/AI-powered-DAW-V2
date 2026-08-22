"""
Track Panel with Volume, Pan, Mute, Solo Controls
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QSlider, QPushButton, QFrame, QScrollArea, 
    QLineEdit, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPalette


class TrackPanel(QWidget):
    """Panel for track controls (volume, pan, mute, solo)"""
    
    # Signals
    track_selected = pyqtSignal(int)
    volume_changed = pyqtSignal(int, float)
    pan_changed = pyqtSignal(int, float)
    mute_changed = pyqtSignal(int, bool)
    solo_changed = pyqtSignal(int, bool)
    track_renamed = pyqtSignal(int, str)
    track_removed = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.tracks = {}  # track_id: TrackWidget
        self.selected_track_id = None
        self.next_track_id = 0
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Set up the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 30, 0, 0)  # Space for ruler
        layout.setSpacing(0)
        
        # Header
        header = QLabel("Tracks")
        header.setStyleSheet("font-weight: bold; padding: 5px; background: #333;")
        header.setFixedHeight(30)
        layout.addWidget(header)
        
        # Scroll area for tracks
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Container for track widgets
        self.track_container = QWidget()
        self.track_layout = QVBoxLayout(self.track_container)
        self.track_layout.setContentsMargins(0, 0, 0, 0)
        self.track_layout.setSpacing(2)
        self.track_layout.addStretch()
        
        self.scroll_area.setWidget(self.track_container)
        layout.addWidget(self.scroll_area)
        
        # Add track button
        self.add_track_btn = QPushButton("+ Add Track")
        self.add_track_btn.setStyleSheet("""
            QPushButton {
                background: #444;
                border: none;
                padding: 8px;
                color: white;
            }
            QPushButton:hover {
                background: #555;
            }
        """)
        self.add_track_btn.clicked.connect(self._on_add_track)
        layout.addWidget(self.add_track_btn)
        
        self.setFixedWidth(250)
        self.setMinimumHeight(400)
        
    def add_track(self, name: str = None) -> int:
        """Add a new track and return its ID"""
        track_id = self.next_track_id
        self.next_track_id += 1
        
        if name is None:
            name = f"Track {track_id + 1}"
            
        track_widget = TrackWidget(track_id, name)
        track_widget.selected.connect(self._on_track_selected)
        track_widget.volume_changed.connect(lambda v, tid=track_id: self.volume_changed.emit(tid, v))
        track_widget.pan_changed.connect(lambda p, tid=track_id: self.pan_changed.emit(tid, p))
        track_widget.mute_changed.connect(lambda m, tid=track_id: self.mute_changed.emit(tid, m))
        track_widget.solo_changed.connect(lambda s, tid=track_id: self.solo_changed.emit(tid, s))
        track_widget.renamed.connect(lambda n, tid=track_id: self.track_renamed.emit(tid, n))
        track_widget.remove_requested.connect(lambda tid=track_id: self._on_remove_track(tid))
        
        # Insert before stretch
        self.track_layout.insertWidget(self.track_layout.count() - 1, track_widget)
        self.tracks[track_id] = track_widget
        
        # Select the new track
        self.select_track(track_id)
        
        return track_id
        
    def remove_track(self, track_id: int):
        """Remove a track"""
        if track_id in self.tracks:
            track_widget = self.tracks[track_id]
            self.track_layout.removeWidget(track_widget)
            track_widget.deleteLater()
            del self.tracks[track_id]
            
            if self.selected_track_id == track_id:
                self.selected_track_id = None
                
    def select_track(self, track_id: int):
        """Select a track"""
        # Deselect all
        for track in self.tracks.values():
            track.set_selected(False)
            
        # Select new track
        if track_id in self.tracks:
            self.tracks[track_id].set_selected(True)
            self.selected_track_id = track_id
            self.track_selected.emit(track_id)
            
    def get_selected_track(self) -> int:
        """Get the selected track ID"""
        return self.selected_track_id
        
    def set_track_volume(self, track_id: int, volume: float):
        """Set track volume"""
        if track_id in self.tracks:
            self.tracks[track_id].set_volume(volume)
            
    def set_track_pan(self, track_id: int, pan: float):
        """Set track pan"""
        if track_id in self.tracks:
            self.tracks[track_id].set_pan(pan)
            
    def set_track_mute(self, track_id: int, muted: bool):
        """Set track mute"""
        if track_id in self.tracks:
            self.tracks[track_id].set_mute(muted)
            
    def set_track_solo(self, track_id: int, soloed: bool):
        """Set track solo"""
        if track_id in self.tracks:
            self.tracks[track_id].set_solo(soloed)
            
    def _on_track_selected(self, track_id: int):
        """Handle track selection"""
        self.select_track(track_id)
        
    def _on_add_track(self):
        """Handle add track button"""
        self.add_track()
        
    def _on_remove_track(self, track_id: int):
        """Handle remove track request"""
        self.track_removed.emit(track_id)
        self.remove_track(track_id)
        
    def clear(self):
        """Clear all tracks"""
        for track_id in list(self.tracks.keys()):
            self.remove_track(track_id)
        self.next_track_id = 0
        self.selected_track_id = None
        
    def get_state(self):
        """Get panel state for saving"""
        return {
            'tracks': {
                tid: {
                    'name': track.name,
                    'volume': track.get_volume(),
                    'pan': track.get_pan(),
                    'muted': track.is_muted(),
                    'soloed': track.is_soloed()
                }
                for tid, track in self.tracks.items()
            },
            'next_track_id': self.next_track_id
        }
        
    def set_state(self, state):
        """Set panel state from loaded project"""
        self.clear()
        
        if 'tracks' in state:
            for track_id, track_data in state['tracks'].items():
                self.add_track(track_data.get('name', f"Track {track_id}"))
                self.set_track_volume(track_id, track_data.get('volume', 1.0))
                self.set_track_pan(track_id, track_data.get('pan', 0.0))
                self.set_track_mute(track_id, track_data.get('muted', False))
                self.set_track_solo(track_id, track_data.get('soloed', False))
                
        if 'next_track_id' in state:
            self.next_track_id = state['next_track_id']


class TrackWidget(QFrame):
    """Individual track control widget"""
    
    selected = pyqtSignal(int)
    volume_changed = pyqtSignal(float)
    pan_changed = pyqtSignal(float)
    mute_changed =pyqtSignal(bool)
    solo_changed = pyqtSignal(bool)
    renamed = pyqtSignal(str)
    remove_requested = pyqtSignal()
    
    def __init__(self, track_id: int, name: str, parent=None):
        super().__init__(parent)
        
        self.track_id = track_id
        self.name = name
        self.is_selected = False
        
        self._setup_ui()
        self._update_style()
        
    def _setup_ui(self):
        """Set up the UI"""
        self.setFixedHeight(80)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Left column: Name and buttons
        left_col = QVBoxLayout()
        
        # Track name
        self.name_edit = QLineEdit(self.name)
        self.name_edit.setFixedWidth(100)
        self.name_edit.setStyleSheet("background: #333; color: white; border: 1px solid #555;")
        self.name_edit.editingFinished.connect(self._on_rename)
        left_col.addWidget(self.name_edit)
        
        # Mute/Solo buttons
        btn_layout = QHBoxLayout()
        
        self.mute_btn = QPushButton("M")
        self.mute_btn.setFixedSize(25, 25)
        self.mute_btn.setCheckable(True)
        self.mute_btn.setStyleSheet("""
            QPushButton {
                background: #444;
                color: #888;
                border: none;
                font-weight: bold;
            }
            QPushButton:checked {
                background: #ff6b6b;
                color: white;
            }
        """)
        self.mute_btn.toggled.connect(self.mute_changed.emit)
        btn_layout.addWidget(self.mute_btn)
        
        self.solo_btn = QPushButton("S")
        self.solo_btn.setFixedSize(25, 25)
        self.solo_btn.setCheckable(True)
        self.solo_btn.setStyleSheet("""
            QPushButton {
                background: #444;
                color: #888;
                border: none;
                font-weight: bold;
            }
            QPushButton:checked {
                background: #ffd93d;
                color: black;
            }
        """)
        self.solo_btn.toggled.connect(self.solo_changed.emit)
        btn_layout.addWidget(self.solo_btn)
        
        self.remove_btn = QPushButton("×")
        self.remove_btn.setFixedSize(25, 25)
        self.remove_btn.setStyleSheet("""
            QPushButton {
                background: #444;
                color: #888;
                border: none;
            }
            QPushButton:hover {
                background: #ff6b6b;
                color: white;
            }
        """)
        self.remove_btn.clicked.connect(self.remove_requested.emit)
        btn_layout.addWidget(self.remove_btn)
        
        left_col.addLayout(btn_layout)
        layout.addLayout(left_col)
        
        # Right column: Volume and Pan
        right_col = QVBoxLayout()
        
        # Volume slider
        vol_layout = QHBoxLayout()
        vol_layout.addWidget(QLabel("Vol"))
        
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        vol_layout.addWidget(self.volume_slider)
        
        self.volume_label = QLabel("100%")
        self.volume_label.setFixedWidth(35)
        vol_layout.addWidget(self.volume_label)
        
        right_col.addLayout(vol_layout)
        
        # Pan slider
        pan_layout = QHBoxLayout()
        pan_layout.addWidget(QLabel("Pan"))
        
        self.pan_slider = QSlider(Qt.Orientation.Horizontal)
        self.pan_slider.setRange(-50, 50)
        self.pan_slider.setValue(0)
        self.pan_slider.setFixedWidth(80)
        self.pan_slider.valueChanged.connect(self._on_pan_changed)
        pan_layout.addWidget(self.pan_slider)
        
        self.pan_label = QLabel("C")
        self.pan_label.setFixedWidth(35)
        pan_layout.addWidget(self.pan_label)
        
        right_col.addLayout(pan_layout)
        layout.addLayout(right_col)
        
    def _update_style(self):
        """Update widget style based on selection state"""
        if self.is_selected:
            self.setStyleSheet("""
                TrackWidget {
                    background: #3a3a4a;
                    border: 2px solid #6a9eff;
                }
            """)
        else:
            self.setStyleSheet("""
                TrackWidget {
                    background: #2a2a2a;
                    border: 1px solid #444;
                }
            """)
            
    def set_selected(self, selected: bool):
        """Set selected state"""
        self.is_selected = selected
        self._update_style()
        
    def mousePressEvent(self, event):
        """Handle mouse press"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.track_id)
        super().mousePressEvent(event)
        
    def _on_volume_changed(self, value):
        """Handle volume slider change"""
        volume = value / 100.0
        self.volume_label.setText(f"{value}%")
        self.volume_changed.emit(volume)
        
    def _on_pan_changed(self, value):
        """Handle pan slider change"""
        pan = value / 50.0
        if value == 0:
            self.pan_label.setText("C")
        elif value < 0:
            self.pan_label.setText(f"L{abs(value)}")
        else:
            self.pan_label.setText(f"R{value}")
        self.pan_changed.emit(pan)
        
    def _on_rename(self):
        """Handle track rename"""
        self.name = self.name_edit.text()
        self.renamed.emit(self.name)
        
    def set_volume(self, volume: float):
        """Set volume (0.0 to 1.0)"""
        value = int(volume * 100)
        self.volume_slider.setValue(value)
        self.volume_label.setText(f"{value}%")
        
    def set_pan(self, pan: float):
        """Set pan (-1.0 to 1.0)"""
        value = int(pan * 50)
        self.pan_slider.setValue(value)
        
    def set_mute(self, muted: bool):
        """Set mute state"""
        self.mute_btn.setChecked(muted)
        
    def set_solo(self, soloed: bool):
        """Set solo state"""
        self.solo_btn.setChecked(soloed)
        
    def get_volume(self) -> float:
        """Get current volume"""
        return self.volume_slider.value() / 100.0
        
    def get_pan(self) -> float:
        """Get current pan"""
        return self.pan_slider.value() / 50.0
        
    def is_muted(self) -> bool:
        """Check if muted"""
        return self.mute_btn.isChecked()
        
    def is_soloed(self) -> bool:
        """Check if soloed"""
        return self.solo_btn.isChecked()
