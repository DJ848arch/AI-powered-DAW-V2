"""
Transport Controls - BPM, Time Signature, Metronome UI
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, 
    QLabel, QSpinBox, QComboBox, QFrame, QLCDNumber
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont


class TransportControls(QWidget):
    """Transport controls with play, pause, stop, record, BPM, time signature"""
    
    # Signals
    play_clicked = pyqtSignal()
    pause_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    record_clicked = pyqtSignal()
    bpm_changed = pyqtSignal(int)
    time_signature_changed = pyqtSignal(int, int)
    metronome_toggled = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.is_playing = False
        self.is_recording = False
        self.bpm = 120
        self.beats_per_bar = 4
        self.beat_unit = 4
        self.metronome_active = False
        self.current_time = 0.0
        
        self._setup_ui()
        self._setup_timer()
        
    def _setup_ui(self):
        """Set up the UI"""
        self.setFixedHeight(80)
        self.setStyleSheet("""
            TransportControls {
                background: #2a2a2a;
                border-bottom: 1px solid #444;
            }
            QPushButton {
                background: #444;
                border: 1px solid #555;
                border-radius: 4px;
                color: white;
                padding: 8px 16px;
                font-weight: bold;
                min-width: 50px;
            }
            QPushButton:hover {
                background: #555;
            }
            QPushButton:pressed {
                background: #666;
            }
            QPushButton:checked {
                background: #6a9eff;
            }
            QLabel {
                color: #ccc;
                font-size: 11px;
            }
            QSpinBox, QComboBox {
                background: #333;
                border: 1px solid #555;
                color: white;
                padding: 4px;
            }
            QLCDNumber {
                background: #1a1a1a;
                color: #6a9eff;
                border: 2px solid #444;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # Time display
        time_layout = QVBoxLayout()
        time_layout.addWidget(QLabel("Time"))
        
        self.time_display = QLCDNumber(8)
        self.time_display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
        self.time_display.setFixedSize(120, 40)
        self.time_display.display("00:00:00")
        time_layout.addWidget(self.time_display)
        
        layout.addLayout(time_layout)
        
        # Separator
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.VLine)
        separator1.setStyleSheet("color: #444;")
        layout.addWidget(separator1)
        
        # Transport buttons
        transport_layout = QHBoxLayout()
        transport_layout.setSpacing(5)
        
        # Stop button
        self.stop_btn = QPushButton("⏹")
        self.stop_btn.setToolTip("Stop (Space)")
        self.stop_btn.clicked.connect(self._on_stop)
        transport_layout.addWidget(self.stop_btn)
        
        # Play button
        self.play_btn = QPushButton("▶")
        self.play_btn.setToolTip("Play (Space)")
        self.play_btn.setCheckable(True)
        self.play_btn.clicked.connect(self._on_play)
        transport_layout.addWidget(self.play_btn)
        
        # Pause button
        self.pause_btn = QPushButton("⏸")
        self.pause_btn.setToolTip("Pause")
        self.pause_btn.clicked.connect(self._on_pause)
        transport_layout.addWidget(self.pause_btn)
        
        # Record button
        self.record_btn = QPushButton("⏺")
        self.record_btn.setToolTip("Record (R)")
        self.record_btn.setCheckable(True)
        self.record_btn.setStyleSheet("""
            QPushButton {
                background: #444;
                border: 1px solid #555;
                border-radius: 4px;
                color: #ff6b6b;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:checked {
                background: #ff6b6b;
                color: white;
            }
        """)
        self.record_btn.clicked.connect(self._on_record)
        transport_layout.addWidget(self.record_btn)
        
        layout.addLayout(transport_layout)
        
        # Separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.VLine)
        separator2.setStyleSheet("color: #444;")
        layout.addWidget(separator2)
        
        # BPM controls
        bpm_layout = QVBoxLayout()
        bpm_layout.addWidget(QLabel("BPM"))
        
        bpm_spin_layout = QHBoxLayout()
        self.bpm_spin = QSpinBox()
        self.bpm_spin.setRange(1, 300)
        self.bpm_spin.setValue(self.bpm)
        self.bpm_spin.setFixedWidth(60)
        self.bpm_spin.valueChanged.connect(self._on_bpm_changed)
        bpm_spin_layout.addWidget(self.bpm_spin)
        
        # Tap tempo button
        self.tap_btn = QPushButton("Tap")
        self.tap_btn.setToolTip("Tap Tempo")
        self.tap_btn.setFixedWidth(40)
        self.tap_btn.clicked.connect(self._on_tap_tempo)
        bpm_spin_layout.addWidget(self.tap_btn)
        
        bpm_layout.addLayout(bpm_spin_layout)
        layout.addLayout(bpm_layout)
        
        # Time signature
        sig_layout = QVBoxLayout()
        sig_layout.addWidget(QLabel("Time Sig"))
        
        sig_combo_layout = QHBoxLayout()
        
        self.beats_combo = QComboBox()
        self.beats_combo.addItems(["2", "3", "4", "5", "6", "7", "8", "9", "12"])
        self.beats_combo.setCurrentText("4")
        self.beats_combo.setFixedWidth(45)
        self.beats_combo.currentTextChanged.connect(self._on_time_signature_changed)
        sig_combo_layout.addWidget(self.beats_combo)
        
        sig_combo_layout.addWidget(QLabel("/"))
        
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["2", "4", "8", "16"])
        self.unit_combo.setCurrentText("4")
        self.unit_combo.setFixedWidth(45)
        self.unit_combo.currentTextChanged.connect(self._on_time_signature_changed)
        sig_combo_layout.addWidget(self.unit_combo)
        
        sig_layout.addLayout(sig_combo_layout)
        layout.addLayout(sig_layout)
        
        # Metronome
        metro_layout = QVBoxLayout()
        metro_layout.addWidget(QLabel("Metronome"))
        
        self.metro_btn = QPushButton("🎵")
        self.metro_btn.setToolTip("Toggle Metronome")
        self.metro_btn.setCheckable(True)
        self.metro_btn.setFixedSize(40, 30)
        self.metro_btn.clicked.connect(self._on_metronome_toggled)
        metro_layout.addWidget(self.metro_btn)
        
        layout.addLayout(metro_layout)
        
        # Separator
        separator3 = QFrame()
        separator3.setFrameShape(QFrame.Shape.VLine)
        separator3.setStyleSheet("color: #444;")
        layout.addWidget(separator3)
        
        # Beat counter
        beat_layout = QVBoxLayout()
        beat_layout.addWidget(QLabel("Beat"))
        
        self.beat_display = QLCDNumber(3)
        self.beat_display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
        self.beat_display.setFixedSize(60, 40)
        self.beat_display.display("1.1")
        beat_layout.addWidget(self.beat_display)
        
        layout.addLayout(beat_layout)
        
        layout.addStretch()
        
    def _setup_timer(self):
        """Set up update timer"""
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_display)
        self.update_timer.setInterval(50)  # 20 FPS
        
        # Tap tempo timer
        self.tap_times = []
        self.tap_timer = QTimer(self)
        self.tap_timer.setSingleShot(True)
        self.tap_timer.timeout.connect(self._clear_tap_times)
        
    def _on_play(self, checked):
        """Handle play button"""
        if checked:
            self.is_playing = True
            self.play_btn.setText("⏸")
            self.update_timer.start()
            self.play_clicked.emit()
        else:
            self._on_pause()
            
    def _on_pause(self):
        """Handle pause button"""
        self.is_playing = False
        self.play_btn.setChecked(False)
        self.play_btn.setText("▶")
        self.update_timer.stop()
        self.pause_clicked.emit()
        
    def _on_stop(self):
        """Handle stop button"""
        self.is_playing = False
        self.is_recording = False
        self.current_time = 0.0
        
        self.play_btn.setChecked(False)
        self.play_btn.setText("▶")
        self.record_btn.setChecked(False)
        
        self.update_timer.stop()
        self._update_display()
        
        self.stop_clicked.emit()
        
    def _on_record(self, checked):
        """Handle record button"""
        self.is_recording = checked
        if checked:
            # Auto-start playback when recording
            if not self.is_playing:
                self.play_btn.setChecked(True)
                self._on_play(True)
        self.record_clicked.emit()
        
    def _on_bpm_changed(self, value):
        """Handle BPM change"""
        self.bpm = value
        self.bpm_changed.emit(value)
        
    def _on_time_signature_changed(self):
        """Handle time signature change"""
        self.beats_per_bar = int(self.beats_combo.currentText())
        self.beat_unit = int(self.unit_combo.currentText())
        self.time_signature_changed.emit(self.beats_per_bar, self.beat_unit)
        
    def _on_metronome_toggled(self, checked):
        """Handle metronome toggle"""
        self.metronome_active = checked
        self.metronome_toggled.emit(checked)
        
    def _on_tap_tempo(self):
        """Handle tap tempo"""
        current_time = self._get_current_time_ms()
        self.tap_times.append(current_time)
        
        # Keep only last 8 taps
        if len(self.tap_times) > 8:
            self.tap_times.pop(0)
            
        # Calculate BPM from intervals
        if len(self.tap_times) >= 2:
            intervals = []
            for i in range(1, len(self.tap_times)):
                interval = self.tap_times[i] - self.tap_times[i-1]
                if 200 < interval < 2000:  # Reasonable tempo range
                    intervals.append(interval)
                    
            if intervals:
                avg_interval = sum(intervals) / len(intervals)
                bpm = int(60000 / avg_interval)
                bpm = max(1, min(300, bpm))
                self.bpm_spin.setValue(bpm)
                
        # Reset tap timer
        self.tap_timer.start(2000)  # Clear after 2 seconds
        
    def _clear_tap_times(self):
        """Clear tap tempo times"""
        self.tap_times = []
        
    def _get_current_time_ms(self):
        """Get current time in milliseconds"""
        from PyQt6.QtCore import QTime
        return QTime.currentTime().msec() + QTime.currentTime().second() * 1000 + QTime.currentTime().minute() * 60000
        
    def _update_display(self):
        """Update time display"""
        if self.is_playing:
            self.current_time += 0.05  # 50ms increments
            
        # Format time display
        minutes = int(self.current_time // 60)
        seconds = int(self.current_time % 60)
        millis = int((self.current_time % 1) * 100)
        
        time_str = f"{minutes:02d}:{seconds:02d}:{millis:02d}"
        self.time_display.display(time_str)
        
        # Calculate beat position
        beat_duration = 60.0 / self.bpm
        total_beats = self.current_time / beat_duration
        
        bar = int(total_beats // self.beats_per_bar) + 1
        beat = int(total_beats % self.beats_per_bar) + 1
        
        self.beat_display.display(f"{bar}.{beat}")
        
    def set_position(self, position: float):
        """Set playback position"""
        self.current_time = position
        self._update_display()
        
    def set_bpm(self, bpm: int):
        """Set BPM"""
        self.bpm = bpm
        self.bpm_spin.setValue(bpm)
        
    def set_time_signature(self, beats: int, unit: int):
        """Set time signature"""
        self.beats_per_bar = beats
        self.beat_unit = unit
        self.beats_combo.setCurrentText(str(beats))
        self.unit_combo.setCurrentText(str(unit))
        
    def get_state(self):
        """Get transport state for saving"""
        return {
            'bpm': self.bpm,
            'beats_per_bar': self.beats_per_bar,
            'beat_unit': self.beat_unit,
            'metronome_active': self.metronome_active,
            'position': self.current_time
        }
        
    def set_state(self, state):
        """Set transport state from loaded project"""
        if 'bpm' in state:
            self.set_bpm(state['bpm'])
        if 'beats_per_bar' in state:
            self.beats_per_bar = state['beats_per_bar']
        if 'beat_unit' in state:
            self.beat_unit = state['beat_unit']
        if 'metronome_active' in state:
            self.metro_btn.setChecked(state['metronome_active'])
            self.metronome_active = state['metronome_active']
        if 'position' in state:
            self.set_position(state['position'])
