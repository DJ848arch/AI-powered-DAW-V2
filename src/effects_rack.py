"""
Audio Effects Rack UI
Placeholder for audio effects processing

Insert DSP (M2): a documented, ordered chain of built-in stages.
No VST, plugin hosting, or marketplace. AudioEngine applies
apply_insert_chain(slots, audio) on each channel (track or bus)
after clips are summed and before mute/solo/volume/pan and the
split to main output + sends.

Built-in types (see SCHEMA.md):
  identity / passthru — no-op
  gain                — multiply by ``gain`` (default 1.0)
  offset              — add ``amount`` (default 0.0); proves chain order

Empty ``[]`` is dry/identity. ``enabled: false`` bypasses that slot.
Unknown types are treated as identity. Tests may still install a fake
insert via set_test_insert (M1 hook).
"""

import math

import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QSlider, QPushButton, QComboBox, QFrame,
    QScrollArea, QGroupBox, QCheckBox, QSpinBox,
    QDoubleSpinBox, QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor


# Track_id -> callable(audio) -> audio. Test-only; not persisted.
_TEST_INSERTS = {}

# Documented built-in processors. Not a plugin host.
INSERT_TYPES = ("identity", "passthru", "gain", "offset")


def apply_insert_chain(audio, slots):
    """Apply an ordered insert chain. Empty / None is identity (same object).

    Each slot is a dict. Unknown keys are ignored by the processor but
    kept on the slot by the engine. Disabled and unknown types are dry.
    """
    if audio is None:
        return audio
    if not slots:
        return audio
    out = audio
    mutated = False
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        if slot.get("enabled", True) is False:
            continue
        typ = str(slot.get("type") or "identity").strip().lower()
        if typ in ("identity", "passthru", ""):
            continue
        if typ == "gain":
            try:
                gain = float(slot.get("gain", 1.0))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(gain) or gain == 1.0:
                continue
            if not mutated:
                out = audio * np.float32(gain)
                mutated = True
            else:
                out = out * np.float32(gain)
        elif typ == "offset":
            try:
                amount = float(slot.get("amount", 0.0))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(amount) or amount == 0.0:
                continue
            if not mutated:
                out = audio + np.float32(amount)
                mutated = True
            else:
                out = out + np.float32(amount)
        # unknown type: identity
    return out


def apply_inserts(track_id, audio):
    """Apply on-channel inserts. Identity when the rack has no DSP.

    Returns ``audio`` unchanged (dry) unless a test insert is installed
    for this track. Does not process other tracks, buses, or master.
    """
    if audio is None:
        return audio
    try:
        if isinstance(track_id, bool):
            key = track_id
        else:
            key = int(track_id)
    except (TypeError, ValueError):
        key = track_id
    fn = _TEST_INSERTS.get(key)
    if fn is None:
        return audio
    out = fn(audio)
    return audio if out is None else out


def set_test_insert(track_id, fn=None, gain=None):
    """Test-only: install a fake on-channel insert. Not a real effect.

    ``fn`` is ``callable(audio) -> audio``. ``gain`` is a scalar multiply
    (e.g. 0.5) used to characterize mix order. Pass neither to clear
    the insert on this track.
    """
    try:
        if isinstance(track_id, bool):
            key = track_id
        else:
            key = int(track_id)
    except (TypeError, ValueError):
        key = track_id
    if fn is None and gain is not None:
        g = float(gain)

        def fn(audio, _g=g):
            if audio is None:
                return audio
            return audio * _g

    if fn is None:
        _TEST_INSERTS.pop(key, None)
        return
    _TEST_INSERTS[key] = fn


def clear_test_insert(track_id):
    """Remove the test insert for one channel (track id or bus name)."""
    set_test_insert(track_id)


def clear_test_inserts():
    """Remove all test inserts (test isolation)."""
    _TEST_INSERTS.clear()


class EffectsRack(QWidget):
    """Audio effects rack for tracks"""
    
    # Signals
    effect_enabled = pyqtSignal(int, str, bool)
    effect_param_changed = pyqtSignal(int, str, str, float)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.effects = {}  # effect_id: EffectWidget
        self.track_id = None
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Set up the UI"""
        self.setStyleSheet("""
            EffectsRack {
                background: #2a2a2a;
            }
            QGroupBox {
                background: #333;
                border: 1px solid #555;
                border-radius: 4px;
                margin-top: 10px;
                font-weight: bold;
                color: #ccc;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLabel {
                color: #aaa;
                font-size: 11px;
            }
            QSlider::groove:horizontal {
                background: #444;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #6a9eff;
                width: 12px;
                height: 12px;
                margin: -3px 0;
                border-radius: 6px;
            }
            QCheckBox {
                color: #ccc;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QComboBox {
                background: #444;
                border: 1px solid #555;
                color: white;
                padding: 4px;
            }
            QPushButton {
                background: #444;
                border: 1px solid #555;
                color: white;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background: #555;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        
        # Header
        header = QLabel("🎛️ Effects Rack")
        header.setStyleSheet("font-size: 14px; font-weight: bold; color: #6a9eff;")
        layout.addWidget(header)
        
        # Track selector
        track_layout = QHBoxLayout()
        track_layout.addWidget(QLabel("Track:"))
        self.track_combo = QComboBox()
        self.track_combo.setMinimumWidth(150)
        track_layout.addWidget(self.track_combo)
        track_layout.addStretch()
        layout.addLayout(track_layout)
        
        # Effects tabs
        self.tabs = QTabWidget()
        
        # EQ Tab
        eq_widget = self._create_eq_tab()
        self.tabs.addTab(eq_widget, "EQ")
        
        # Dynamics Tab
        dynamics_widget = self._create_dynamics_tab()
        self.tabs.addTab(dynamics_widget, "Dynamics")
        
        # Reverb Tab
        reverb_widget = self._create_reverb_tab()
        self.tabs.addTab(reverb_widget, "Reverb")
        
        # Delay Tab
        delay_widget = self._create_delay_tab()
        self.tabs.addTab(delay_widget, "Delay")
        
        # Modulation Tab
        mod_widget = self._create_modulation_tab()
        self.tabs.addTab(mod_widget, "Modulation")
        
        layout.addWidget(self.tabs)
        
        # Add effect button
        self.add_effect_btn = QPushButton("+ Add Effect")
        self.add_effect_btn.setStyleSheet("""
            QPushButton {
                background: #4a9eff;
                border: none;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #5aafff;
            }
        """)
        self.add_effect_btn.clicked.connect(self._show_add_effect_menu)
        layout.addWidget(self.add_effect_btn)
        
        # Effect chain display
        self.chain_label = QLabel("Effect Chain: (empty)")
        self.chain_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self.chain_label)
        
        layout.addStretch()
        
    def _create_eq_tab(self):
        """Create EQ controls"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Enable EQ
        self.eq_enable = QCheckBox("Enable EQ")
        layout.addWidget(self.eq_enable)
        
        # EQ bands
        eq_frame = QFrame()
        eq_layout = QVBoxLayout(eq_frame)
        
        # Low shelf
        low_group = QGroupBox("Low Shelf (100 Hz)")
        low_layout = QHBoxLayout(low_group)
        
        low_layout.addWidget(QLabel("Gain:"))
        self.low_gain = QSlider(Qt.Orientation.Horizontal)
        self.low_gain.setRange(-120, 120)
        self.low_gain.setValue(0)
        self.low_gain.setTickPosition(QSlider.TickPosition.TicksBelow)
        low_layout.addWidget(self.low_gain)
        
        self.low_gain_label = QLabel("0 dB")
        self.low_gain_label.setFixedWidth(40)
        low_layout.addWidget(self.low_gain_label)
        
        eq_layout.addWidget(low_group)
        
        # Mid band
        mid_group = QGroupBox("Mid Band (1 kHz)")
        mid_layout = QHBoxLayout(mid_group)
        
        mid_layout.addWidget(QLabel("Gain:"))
        self.mid_gain = QSlider(Qt.Orientation.Horizontal)
        self.mid_gain.setRange(-120, 120)
        self.mid_gain.setValue(0)
        mid_layout.addWidget(self.mid_gain)
        
        self.mid_gain_label = QLabel("0 dB")
        self.mid_gain_label.setFixedWidth(40)
        mid_layout.addWidget(self.mid_gain_label)
        
        eq_layout.addWidget(mid_group)
        
        # High shelf
        high_group = QGroupBox("High Shelf (10 kHz)")
        high_layout = QHBoxLayout(high_group)
        
        high_layout.addWidget(QLabel("Gain:"))
        self.high_gain = QSlider(Qt.Orientation.Horizontal)
        self.high_gain.setRange(-120, 120)
        self.high_gain.setValue(0)
        high_layout.addWidget(self.high_gain)
        
        self.high_gain_label = QLabel("0 dB")
        self.high_gain_label.setFixedWidth(40)
        high_layout.addWidget(self.high_gain_label)
        
        eq_layout.addWidget(high_group)
        
        layout.addWidget(eq_frame)
        layout.addStretch()
        
        return widget
        
    def _create_dynamics_tab(self):
        """Create dynamics controls (compressor, limiter)"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Compressor
        comp_group = QGroupBox("Compressor")
        comp_layout = QVBoxLayout(comp_group)
        
        # Enable
        self.comp_enable = QCheckBox("Enable Compressor")
        comp_layout.addWidget(self.comp_enable)
        
        # Threshold
        thresh_layout = QHBoxLayout()
        thresh_layout.addWidget(QLabel("Threshold:"))
        self.comp_threshold = QSlider(Qt.Orientation.Horizontal)
        self.comp_threshold.setRange(-600, 0)
        self.comp_threshold.setValue(-200)
        thresh_layout.addWidget(self.comp_threshold)
        thresh_layout.addWidget(QLabel("-20 dB"))
        comp_layout.addLayout(thresh_layout)
        
        # Ratio
        ratio_layout = QHBoxLayout()
        ratio_layout.addWidget(QLabel("Ratio:"))
        self.comp_ratio = QSlider(Qt.Orientation.Horizontal)
        self.comp_ratio.setRange(10, 200)
        self.comp_ratio.setValue(40)
        ratio_layout.addWidget(self.comp_ratio)
        ratio_layout.addWidget(QLabel("4:1"))
        comp_layout.addLayout(ratio_layout)
        
        # Attack
        attack_layout = QHBoxLayout()
        attack_layout.addWidget(QLabel("Attack:"))
        self.comp_attack = QSlider(Qt.Orientation.Horizontal)
        self.comp_attack.setRange(1, 100)
        self.comp_attack.setValue(10)
        attack_layout.addWidget(self.comp_attack)
        attack_layout.addWidget(QLabel("10 ms"))
        comp_layout.addLayout(attack_layout)
        
        # Release
        release_layout = QHBoxLayout()
        release_layout.addWidget(QLabel("Release:"))
        self.comp_release = QSlider(Qt.Orientation.Horizontal)
        self.comp_release.setRange(10, 1000)
        self.comp_release.setValue(100)
        release_layout.addWidget(self.comp_release)
        release_layout.addWidget(QLabel("100 ms"))
        comp_layout.addLayout(release_layout)
        
        layout.addWidget(comp_group)
        
        # Limiter
        limit_group = QGroupBox("Limiter")
        limit_layout = QVBoxLayout(limit_group)
        
        self.limit_enable = QCheckBox("Enable Limiter")
        limit_layout.addWidget(self.limit_enable)
        
        limit_ceiling_layout = QHBoxLayout()
        limit_ceiling_layout.addWidget(QLabel("Ceiling:"))
        self.limit_ceiling = QSlider(Qt.Orientation.Horizontal)
        self.limit_ceiling.setRange(-100, 0)
        self.limit_ceiling.setValue(-10)
        limit_ceiling_layout.addWidget(self.limit_ceiling)
        limit_ceiling_layout.addWidget(QLabel("-1 dB"))
        limit_layout.addLayout(limit_ceiling_layout)
        
        layout.addWidget(limit_group)
        layout.addStretch()
        
        return widget
        
    def _create_reverb_tab(self):
        """Create reverb controls"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        self.reverb_enable = QCheckBox("Enable Reverb")
        layout.addWidget(self.reverb_enable)
        
        reverb_group = QGroupBox("Reverb Settings")
        reverb_layout = QVBoxLayout(reverb_group)
        
        # Room size
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Room Size:"))
        self.reverb_size = QSlider(Qt.Orientation.Horizontal)
        self.reverb_size.setRange(0, 100)
        self.reverb_size.setValue(50)
        size_layout.addWidget(self.reverb_size)
        size_layout.addWidget(QLabel("50%"))
        reverb_layout.addLayout(size_layout)
        
        # Damping
        damp_layout = QHBoxLayout()
        damp_layout.addWidget(QLabel("Damping:"))
        self.reverb_damp = QSlider(Qt.Orientation.Horizontal)
        self.reverb_damp.setRange(0, 100)
        self.reverb_damp.setValue(50)
        damp_layout.addWidget(self.reverb_damp)
        damp_layout.addWidget(QLabel("50%"))
        reverb_layout.addLayout(damp_layout)
        
        # Wet/Dry mix
        mix_layout = QHBoxLayout()
        mix_layout.addWidget(QLabel("Mix:"))
        self.reverb_mix = QSlider(Qt.Orientation.Horizontal)
        self.reverb_mix.setRange(0, 100)
        self.reverb_mix.setValue(30)
        mix_layout.addWidget(self.reverb_mix)
        mix_layout.addWidget(QLabel("30%"))
        reverb_layout.addLayout(mix_layout)
        
        # Pre-delay
        predelay_layout = QHBoxLayout()
        predelay_layout.addWidget(QLabel("Pre-delay:"))
        self.reverb_predelay = QSlider(Qt.Orientation.Horizontal)
        self.reverb_predelay.setRange(0, 200)
        self.reverb_predelay.setValue(20)
        predelay_layout.addWidget(self.reverb_predelay)
        predelay_layout.addWidget(QLabel("20 ms"))
        reverb_layout.addLayout(predelay_layout)
        
        layout.addWidget(reverb_group)
        layout.addStretch()
        
        return widget
        
    def _create_delay_tab(self):
        """Create delay controls"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        self.delay_enable = QCheckBox("Enable Delay")
        layout.addWidget(self.delay_enable)
        
        delay_group = QGroupBox("Delay Settings")
        delay_layout = QVBoxLayout(delay_group)
        
        # Delay time
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Time:"))
        self.delay_time = QSlider(Qt.Orientation.Horizontal)
        self.delay_time.setRange(10, 2000)
        self.delay_time.setValue(500)
        time_layout.addWidget(self.delay_time)
        time_layout.addWidget(QLabel("500 ms"))
        delay_layout.addLayout(time_layout)
        
        # Feedback
        feedback_layout = QHBoxLayout()
        feedback_layout.addWidget(QLabel("Feedback:"))
        self.delay_feedback = QSlider(Qt.Orientation.Horizontal)
        self.delay_feedback.setRange(0, 100)
        self.delay_feedback.setValue(40)
        feedback_layout.addWidget(self.delay_feedback)
        feedback_layout.addWidget(QLabel("40%"))
        delay_layout.addLayout(feedback_layout)
        
        # Mix
        mix_layout = QHBoxLayout()
        mix_layout.addWidget(QLabel("Mix:"))
        self.delay_mix = QSlider(Qt.Orientation.Horizontal)
        self.delay_mix.setRange(0, 100)
        self.delay_mix.setValue(30)
        mix_layout.addWidget(self.delay_mix)
        mix_layout.addWidget(QLabel("30%"))
        delay_layout.addLayout(mix_layout)
        
        layout.addWidget(delay_group)
        layout.addStretch()
        
        return widget
        
    def _create_modulation_tab(self):
        """Create modulation controls (chorus, flanger, phaser)"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Chorus
        chorus_group = QGroupBox("Chorus")
        chorus_layout = QVBoxLayout(chorus_group)
        
        self.chorus_enable = QCheckBox("Enable Chorus")
        chorus_layout.addWidget(self.chorus_enable)
        
        rate_layout = QHBoxLayout()
        rate_layout.addWidget(QLabel("Rate:"))
        self.chorus_rate = QSlider(Qt.Orientation.Horizontal)
        self.chorus_rate.setRange(1, 100)
        self.chorus_rate.setValue(20)
        rate_layout.addWidget(self.chorus_rate)
        rate_layout.addWidget(QLabel("2 Hz"))
        chorus_layout.addLayout(rate_layout)
        
        depth_layout = QHBoxLayout()
        depth_layout.addWidget(QLabel("Depth:"))
        self.chorus_depth = QSlider(Qt.Orientation.Horizontal)
        self.chorus_depth.setRange(0, 100)
        self.chorus_depth.setValue(50)
        depth_layout.addWidget(self.chorus_depth)
        depth_layout.addWidget(QLabel("50%"))
        chorus_layout.addLayout(depth_layout)
        
        layout.addWidget(chorus_group)
        
        # Phaser
        phaser_group = QGroupBox("Phaser")
        phaser_layout = QVBoxLayout(phaser_group)
        
        self.phaser_enable = QCheckBox("Enable Phaser")
        phaser_layout.addWidget(self.phaser_enable)
        
        phaser_rate_layout = QHBoxLayout()
        phaser_rate_layout.addWidget(QLabel("Rate:"))
        self.phaser_rate = QSlider(Qt.Orientation.Horizontal)
        self.phaser_rate.setRange(1, 100)
        self.phaser_rate.setValue(10)
        phaser_rate_layout.addWidget(self.phaser_rate)
        phaser_rate_layout.addWidget(QLabel("1 Hz"))
        phaser_layout.addLayout(phaser_rate_layout)
        
        layout.addWidget(phaser_group)
        layout.addStretch()
        
        return widget
        
    def _show_add_effect_menu(self):
        """Show menu to add new effect"""
        # This would show a dialog to add new effects
        pass
        
    def set_track(self, track_id: int, track_name: str):
        """Set the current track"""
        self.track_id = track_id
        # Update track combo
        index = self.track_combo.findText(track_name)
        if index >= 0:
            self.track_combo.setCurrentIndex(index)
            
    def update_track_list(self, tracks: dict):
        """Update the track list"""
        self.track_combo.clear()
        for track_id, track_data in tracks.items():
            name = track_data.get('name', f'Track {track_id}')
            self.track_combo.addItem(name, track_id)
            
    def get_state(self):
        """Get effects state"""
        return {
            'eq_enabled': self.eq_enable.isChecked(),
            'low_gain': self.low_gain.value(),
            'mid_gain': self.mid_gain.value(),
            'high_gain': self.high_gain.value(),
            'comp_enabled': self.comp_enable.isChecked(),
            'reverb_enabled': self.reverb_enable.isChecked(),
            'delay_enabled': self.delay_enable.isChecked(),
        }
        
    def set_state(self, state):
        """Set effects state"""
        if 'eq_enabled' in state:
            self.eq_enable.setChecked(state['eq_enabled'])
        if 'low_gain' in state:
            self.low_gain.setValue(state['low_gain'])
        if 'mid_gain' in state:
            self.mid_gain.setValue(state['mid_gain'])
        if 'high_gain' in state:
            self.high_gain.setValue(state['high_gain'])
