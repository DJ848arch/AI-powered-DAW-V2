"""
Track Panel with Volume, Pan, Mute, Solo Controls
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QPushButton, QFrame, QScrollArea,
    QLineEdit, QSizePolicy, QComboBox, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPalette


def _safe_meter_pair(stats):
    """Normalize engine meter dict to finite peak/rms floats. Never invent levels."""
    if not isinstance(stats, dict):
        return 0.0, 0.0
    try:
        peak = float(stats.get("peak", 0.0) or 0.0)
    except (TypeError, ValueError):
        peak = 0.0
    try:
        rms = float(stats.get("rms", 0.0) or 0.0)
    except (TypeError, ValueError):
        rms = 0.0
    if peak != peak or peak in (float("inf"), float("-inf")):  # NaN / inf
        peak = 0.0
    if rms != rms or rms in (float("inf"), float("-inf")):
        rms = 0.0
    return peak, rms


class MeterReadout(QWidget):
    """Compact peak bar + peak/rms labels. Display-only; values come from engine."""

    def __init__(self, label: str = "", parent=None):
        super().__init__(parent)
        self._peak = 0.0
        self._rms = 0.0
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.name_label = QLabel(label)
        self.name_label.setFixedWidth(48)
        self.name_label.setStyleSheet("color: #bbb; font-size: 10px;")
        row.addWidget(self.name_label)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self.bar.setStyleSheet(
            "QProgressBar { background: #222; border: 1px solid #444; }"
            "QProgressBar::chunk { background: #4caf50; }"
        )
        row.addWidget(self.bar, 1)
        self.value_label = QLabel("0.00 / 0.00")
        self.value_label.setFixedWidth(78)
        self.value_label.setStyleSheet("color: #9ad; font-size: 10px;")
        self.value_label.setToolTip("peak / rms (from engine)")
        row.addWidget(self.value_label)

    def set_label(self, text: str):
        self.name_label.setText(text)

    def set_levels(self, peak: float, rms: float):
        peak, rms = _safe_meter_pair({"peak": peak, "rms": rms})
        self._peak = peak
        self._rms = rms
        # Display scale only — does not compute peak/rms.
        self.bar.setValue(int(max(0.0, min(1.0, peak)) * 1000))
        self.value_label.setText(f"{peak:.2f} / {rms:.2f}")
        if peak >= 0.99:
            chunk = "#e74c3c"
        elif peak >= 0.8:
            chunk = "#f1c40f"
        else:
            chunk = "#4caf50"
        self.bar.setStyleSheet(
            "QProgressBar { background: #222; border: 1px solid #444; }"
            f"QProgressBar::chunk {{ background: {chunk}; }}"
        )

    def get_levels(self):
        return {"peak": self._peak, "rms": self._rms}


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
    output_changed = pyqtSignal(int, object)  # track_id, dest ("master" or int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.tracks = {}  # track_id: TrackWidget
        self.selected_track_id = None
        self.next_track_id = 0
        self.engine = None
        self._bus_meters = {}  # bus name -> MeterReadout
        self._last_meters = {
            "tracks": {},
            "buses": {},
            "master": {"peak": 0.0, "rms": 0.0},
        }
        
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
        
        # Compact meter strip: Master + known buses (not a mixer redesign)
        self.meter_strip = QFrame()
        self.meter_strip.setObjectName("meter_strip")
        self.meter_strip.setStyleSheet(
            "QFrame#meter_strip { background: #2a2a2a; border-top: 1px solid #444; }"
        )
        meter_layout = QVBoxLayout(self.meter_strip)
        meter_layout.setContentsMargins(6, 4, 6, 4)
        meter_layout.setSpacing(2)
        meter_title = QLabel("Meters")
        meter_title.setStyleSheet("color: #888; font-size: 10px; font-weight: bold;")
        meter_layout.addWidget(meter_title)
        self.master_meter = MeterReadout("Master")
        self.master_meter.setObjectName("master_meter")
        meter_layout.addWidget(self.master_meter)
        self.bus_meter_container = QWidget()
        self.bus_meter_layout = QVBoxLayout(self.bus_meter_container)
        self.bus_meter_layout.setContentsMargins(0, 0, 0, 0)
        self.bus_meter_layout.setSpacing(2)
        meter_layout.addWidget(self.bus_meter_container)
        layout.addWidget(self.meter_strip)
        
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
        track_widget.renamed.connect(lambda n, tid=track_id: self._on_track_renamed(tid, n))
        track_widget.remove_requested.connect(lambda tid=track_id: self._on_remove_track(tid))
        track_widget.dest_changed.connect(lambda dest, tid=track_id: self._on_dest_changed(tid, dest))
        
        # Insert before stretch
        self.track_layout.insertWidget(self.track_layout.count() - 1, track_widget)
        self.tracks[track_id] = track_widget
        
        # Select the new track
        self.select_track(track_id)
        self.refresh_dest_options()
        
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
            self.refresh_dest_options()
                
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

    def _on_track_renamed(self, track_id: int, name: str):
        self.track_renamed.emit(track_id, name)
        self.refresh_dest_options()

    def _on_dest_changed(self, track_id: int, dest):
        self.output_changed.emit(track_id, dest)

    def set_engine(self, engine):
        """Use this engine for list_buses() when rebuilding dest options."""
        self.engine = engine
        self.refresh_dest_options()

    def _known_buses(self, engine=None):
        engine = engine if engine is not None else self.engine
        if engine is None or not hasattr(engine, "list_buses"):
            return []
        try:
            names = list(engine.list_buses() or [])
        except Exception:
            return []
        buses = []
        for name in names:
            if not isinstance(name, str):
                continue
            stripped = name.strip()
            if not stripped or stripped.lower() == "master":
                continue
            buses.append(stripped)
        return buses

    def refresh_dest_options(self, engine=None):
        """Master + other tracks + known buses. Never self."""
        peers = [(tid, widget.name) for tid, widget in self.tracks.items()]
        buses = self._known_buses(engine)
        for tid, widget in self.tracks.items():
            options = [("Master", "master")]
            for other_id, name in peers:
                if other_id == tid:
                    continue
                label = name or f"Track {other_id}"
                options.append((label, other_id))
            for bus in buses:
                options.append((bus, bus))
            current = widget.get_dest()
            widget.set_dest_options(options, current)
            new_dest = widget.get_dest()
            if new_dest != current:
                self.output_changed.emit(tid, new_dest)

    def set_track_output(self, track_id: int, dest):
        """Reflect engine dest on the picker without emitting."""
        if track_id in self.tracks:
            self.tracks[track_id].set_dest(dest)

    def get_track_output(self, track_id: int):
        if track_id in self.tracks:
            return self.tracks[track_id].get_dest()
        return "master"

    def sync_outputs_from_engine(self, engine):
        """Rebuild options (including list_buses) and select from get_track_output."""
        if engine is not None:
            self.engine = engine
        self.refresh_dest_options(engine)
        if engine is None:
            return
        for tid, widget in self.tracks.items():
            widget.set_dest(engine.get_track_output(tid))

    def _ensure_bus_meter(self, name: str):
        if name in self._bus_meters:
            return self._bus_meters[name]
        readout = MeterReadout(name)
        readout.setObjectName(f"bus_meter_{name}")
        self.bus_meter_layout.addWidget(readout)
        self._bus_meters[name] = readout
        return readout

    def _prune_bus_meters(self, keep):
        keep_set = set(keep)
        for name in list(self._bus_meters.keys()):
            if name not in keep_set:
                widget = self._bus_meters.pop(name)
                self.bus_meter_layout.removeWidget(widget)
                widget.deleteLater()

    def update_meters_from_engine(self, engine=None):
        """Pull peak/rms from engine.get_meters() into track/bus/Master UI.

        Missing channels show 0.0. Never raises. Does not compute levels.
        """
        engine = engine if engine is not None else self.engine
        zero = {"peak": 0.0, "rms": 0.0}
        try:
            if engine is None or not hasattr(engine, "get_meters"):
                meters = {"tracks": {}, "buses": {}, "master": dict(zero)}
            else:
                meters = engine.get_meters()
                if not isinstance(meters, dict):
                    meters = {"tracks": {}, "buses": {}, "master": dict(zero)}
        except Exception:
            meters = {"tracks": {}, "buses": {}, "master": dict(zero)}

        track_meters = meters.get("tracks") or {}
        bus_meters = meters.get("buses") or {}
        master_stats = meters.get("master") or zero

        # Tracks: use engine dict; missing → zero (also try get_meter if present)
        displayed_tracks = {}
        for tid, widget in self.tracks.items():
            stats = None
            if tid in track_meters:
                stats = track_meters[tid]
            else:
                try:
                    stats = track_meters.get(int(tid))
                except (TypeError, ValueError):
                    stats = None
            if stats is None and engine is not None and hasattr(engine, "get_meter"):
                try:
                    stats = engine.get_meter(tid)
                except Exception:
                    stats = zero
            if stats is None:
                stats = zero
            peak, rms = _safe_meter_pair(stats)
            widget.set_meter(peak, rms)
            displayed_tracks[int(tid)] = {"peak": peak, "rms": rms}

        # Master
        m_peak, m_rms = _safe_meter_pair(master_stats)
        self.master_meter.set_levels(m_peak, m_rms)

        # Buses: known from list_buses + any reported in get_meters
        known = list(self._known_buses(engine))
        for name in bus_meters.keys():
            if isinstance(name, str) and name.strip() and name.strip().lower() != "master":
                if name.strip() not in known:
                    known.append(name.strip())
        self._prune_bus_meters(known)
        displayed_buses = {}
        for name in known:
            stats = bus_meters.get(name)
            if stats is None and engine is not None and hasattr(engine, "get_meter"):
                try:
                    stats = engine.get_meter(name)
                except Exception:
                    stats = zero
            if stats is None:
                stats = zero
            peak, rms = _safe_meter_pair(stats)
            self._ensure_bus_meter(name).set_levels(peak, rms)
            displayed_buses[name] = {"peak": peak, "rms": rms}

        self._last_meters = {
            "tracks": displayed_tracks,
            "buses": displayed_buses,
            "master": {"peak": m_peak, "rms": m_rms},
        }
        return self._last_meters

    def get_displayed_meters(self):
        """Last values shown in the panel (after update_meters_from_engine)."""
        return {
            "tracks": {
                int(k): dict(v) for k, v in self._last_meters.get("tracks", {}).items()
            },
            "buses": {
                str(k): dict(v) for k, v in self._last_meters.get("buses", {}).items()
            },
            "master": dict(
                self._last_meters.get("master") or {"peak": 0.0, "rms": 0.0}
            ),
        }

    def clear_meters(self):
        """Show zeros on all meter widgets (e.g. after stop/clear)."""
        zero = {"peak": 0.0, "rms": 0.0}
        for widget in self.tracks.values():
            widget.set_meter(0.0, 0.0)
        self.master_meter.set_levels(0.0, 0.0)
        for readout in self._bus_meters.values():
            readout.set_levels(0.0, 0.0)
        self._last_meters = {
            "tracks": {int(tid): dict(zero) for tid in self.tracks},
            "buses": {name: dict(zero) for name in self._bus_meters},
            "master": dict(zero),
        }
        
    def clear(self):
        """Clear all tracks"""
        for track_id in list(self.tracks.keys()):
            self.remove_track(track_id)
        self.next_track_id = 0
        self.selected_track_id = None
        self.clear_meters()
        
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
                new_id = self.add_track(track_data.get('name', f"Track {track_id}"))
                self.set_track_volume(new_id, track_data.get('volume', 1.0))
                self.set_track_pan(new_id, track_data.get('pan', 0.0))
                self.set_track_mute(new_id, track_data.get('muted', False))
                self.set_track_solo(new_id, track_data.get('soloed', False))
                
        if 'next_track_id' in state:
            self.next_track_id = state['next_track_id']
        self.refresh_dest_options()


class TrackWidget(QFrame):
    """Individual track control widget"""
    
    selected = pyqtSignal(int)
    volume_changed = pyqtSignal(float)
    pan_changed = pyqtSignal(float)
    mute_changed = pyqtSignal(bool)
    solo_changed = pyqtSignal(bool)
    renamed = pyqtSignal(str)
    remove_requested = pyqtSignal()
    dest_changed = pyqtSignal(object)  # "master" or dest track id
    
    def __init__(self, track_id: int, name: str, parent=None):
        super().__init__(parent)
        
        self.track_id = track_id
        self.name = name
        self.is_selected = False
        self._meter_peak = 0.0
        self._meter_rms = 0.0
        
        self._setup_ui()
        self._update_style()
        
    def _setup_ui(self):
        """Set up the UI"""
        self.setFixedHeight(128)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        
        outer = QVBoxLayout(self)
        outer.setContentsMargins(5, 5, 5, 5)
        outer.setSpacing(4)
        
        layout = QHBoxLayout()
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
        outer.addLayout(layout)
        
        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Out"))
        self.dest_combo = QComboBox()
        self.dest_combo.setObjectName("dest_combo")
        self.dest_combo.setStyleSheet(
            "background: #333; color: white; border: 1px solid #555;"
        )
        self.dest_combo.addItem("Master", "master")
        self.dest_combo.currentIndexChanged.connect(self._on_dest_index_changed)
        dest_row.addWidget(self.dest_combo, 1)
        outer.addLayout(dest_row)

        # Meter row — peak bar + peak/rms from engine only
        self.meter_readout = MeterReadout("Lvl")
        self.meter_readout.setObjectName("track_meter")
        outer.addWidget(self.meter_readout)
        
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

    def _on_dest_index_changed(self, index):
        if index < 0:
            return
        dest = self.dest_combo.itemData(index)
        self.dest_changed.emit(dest)

    def set_dest_options(self, options, current="master"):
        """options: list of (label, value). value is 'master' or track id."""
        combo = self.dest_combo
        combo.blockSignals(True)
        combo.clear()
        for label, value in options:
            combo.addItem(str(label), value)
        self.set_dest(current)
        combo.blockSignals(False)

    def set_dest(self, dest):
        """Select dest without emitting. Unknown dest falls back to Master."""
        combo = self.dest_combo
        combo.blockSignals(True)
        match = -1
        if dest is None or dest == "" or dest == "master":
            want = "master"
        else:
            want = dest
        for i in range(combo.count()):
            data = combo.itemData(i)
            if data == want:
                match = i
                break
            if want != "master":
                try:
                    if int(data) == int(want):
                        match = i
                        break
                except (TypeError, ValueError):
                    pass
        if match < 0:
            match = 0  # Master
        combo.setCurrentIndex(match)
        combo.blockSignals(False)

    def get_dest(self):
        data = self.dest_combo.currentData()
        if data is None or data == "master":
            return "master"
        return data

    def set_meter(self, peak: float, rms: float):
        """Display engine peak/rms. Does not compute levels."""
        peak, rms = _safe_meter_pair({"peak": peak, "rms": rms})
        self._meter_peak = peak
        self._meter_rms = rms
        self.meter_readout.set_levels(peak, rms)

    def get_meter(self):
        return {"peak": self._meter_peak, "rms": self._meter_rms}
        
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
