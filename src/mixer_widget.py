"""Dedicated desktop mixer UI for ARIA.

M3 foundation: expose the M2 engine as channel strips without duplicating
signal-flow state in the UI. The engine remains authoritative.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QScrollArea, QSlider, QVBoxLayout, QWidget,
)


def _meter_value(stats):
    if not isinstance(stats, dict):
        return 0
    try:
        peak = float(stats.get("peak", 0.0) or 0.0)
    except (TypeError, ValueError):
        peak = 0.0
    if peak != peak or peak in (float("inf"), float("-inf")):
        peak = 0.0
    return int(max(0.0, min(1.0, peak)) * 1000)


class MixerChannelStrip(QFrame):
    """One track, bus, or Master strip backed by AudioEngine state."""

    changed = pyqtSignal()

    def __init__(self, channel_id, name, engine, kind="track", parent=None):
        super().__init__(parent)
        self.channel_id = channel_id
        self.engine = engine
        self.kind = kind
        self.setObjectName("mixer_channel_strip")
        self.setMinimumWidth(118)
        self.setMaximumWidth(150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        self.name_label = QLabel(str(name))
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(True)
        layout.addWidget(self.name_label)

        self.meter = QProgressBar()
        self.meter.setRange(0, 1000)
        self.meter.setValue(0)
        self.meter.setTextVisible(False)
        self.meter.setOrientation(Qt.Orientation.Vertical)
        self.meter.setMinimumHeight(110)
        layout.addWidget(self.meter, 1)

        self.fader = QSlider(Qt.Orientation.Vertical)
        self.fader.setRange(0, 100)
        self.fader.setMinimumHeight(130)
        self.fader.valueChanged.connect(self._on_fader)
        layout.addWidget(self.fader, 1, Qt.AlignmentFlag.AlignHCenter)

        self.pan = QSlider(Qt.Orientation.Horizontal)
        self.pan.setRange(-100, 100)
        self.pan.valueChanged.connect(self._on_pan)
        layout.addWidget(QLabel("Pan"))
        layout.addWidget(self.pan)

        self.mute = QPushButton("M")
        self.mute.setCheckable(True)
        self.solo = QPushButton("S")
        self.solo.setCheckable(True)
        buttons = QHBoxLayout()
        buttons.addWidget(self.mute)
        buttons.addWidget(self.solo)
        layout.addLayout(buttons)

        self.output = QComboBox()
        self.output.currentIndexChanged.connect(self._on_output)
        layout.addWidget(QLabel("Output"))
        layout.addWidget(self.output)

        self.insert_summary = QLabel("Inserts: 0")
        self.insert_type = QComboBox()
        self.insert_type.addItems(["identity", "gain", "offset"])
        self.add_insert_button = QPushButton("+ Insert")
        self.add_insert_button.clicked.connect(self._add_insert)
        self.clear_inserts_button = QPushButton("Clear inserts")
        self.clear_inserts_button.clicked.connect(self._clear_inserts)
        layout.addWidget(self.insert_summary)
        layout.addWidget(self.insert_type)
        layout.addWidget(self.add_insert_button)
        layout.addWidget(self.clear_inserts_button)

        self.send_summary = QLabel("Sends: 0")
        self.send_dest = QComboBox()
        self.send_mode = QComboBox()
        self.send_mode.addItems(["post", "pre"])
        self.send_mode.currentTextChanged.connect(self._set_send_mode)
        self.add_send_button = QPushButton("+ Send")
        self.add_send_button.clicked.connect(self._add_send)
        self.send_select = QComboBox()
        self.send_select.currentIndexChanged.connect(self._load_send_editor)
        self.send_level = QSlider(Qt.Orientation.Horizontal)
        self.send_level.setRange(0, 200)
        self.send_level.valueChanged.connect(self._set_send_level)
        self.remove_send_button = QPushButton("Remove send")
        self.remove_send_button.clicked.connect(self._remove_send)
        layout.addWidget(self.send_summary)
        layout.addWidget(self.send_dest)
        layout.addWidget(self.send_mode)
        layout.addWidget(self.add_send_button)
        layout.addWidget(self.send_select)
        layout.addWidget(self.send_level)
        layout.addWidget(self.remove_send_button)

        if self.kind == "track":
            self.mute.toggled.connect(self._on_mute)
            self.solo.toggled.connect(self._on_solo)
        else:
            self.mute.hide()
            self.solo.hide()

        if self.kind == "master":
            self.fader.setEnabled(False)
            self.pan.setEnabled(False)
            self.output.hide()
            for widget in (
                self.insert_summary, self.insert_type, self.add_insert_button,
                self.clear_inserts_button, self.send_summary, self.send_dest,
                self.send_mode, self.add_send_button, self.send_select,
                self.send_level, self.remove_send_button,
            ):
                widget.hide()

        self.sync_from_engine()

    def _track_ids(self):
        ids = set()
        for attr in ("track_volumes", "track_pans", "track_mutes", "track_solos", "track_outputs"):
            mapping = getattr(self.engine, attr, {}) or {}
            for key in mapping:
                try:
                    ids.add(int(key))
                except (TypeError, ValueError):
                    pass
        return sorted(ids)

    def _destinations(self):
        out = [("Master", "master")]
        for tid in self._track_ids():
            if self.kind == "track" and tid == self.channel_id:
                continue
            out.append((f"Track {tid + 1}", tid))
        for bus in self.engine.list_buses():
            if self.kind == "bus" and bus == self.channel_id:
                continue
            out.append((bus, bus))
        return out

    def _set_combo_value(self, value, combo=None):
        combo = combo or self.output
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def sync_from_engine(self):
        blocked = [self.fader.blockSignals(True), self.pan.blockSignals(True),
                   self.mute.blockSignals(True), self.solo.blockSignals(True),
                   self.output.blockSignals(True)]
        try:
            if self.kind == "track":
                tid = int(self.channel_id)
                self.fader.setValue(round(float(self.engine.track_volumes.get(tid, 1.0)) * 100))
                self.pan.setValue(round(float(self.engine.track_pans.get(tid, 0.0)) * 100))
                self.mute.setChecked(bool(self.engine.track_mutes.get(tid, False)))
                self.solo.setChecked(bool(self.engine.track_solos.get(tid, False)))
                dest = self.engine.get_track_output(tid)
            elif self.kind == "bus":
                self.fader.setValue(round(self.engine.get_bus_volume(self.channel_id) * 100))
                self.pan.setValue(round(self.engine.get_bus_pan(self.channel_id) * 100))
                dest = self.engine.get_bus_output(self.channel_id)
            else:
                dest = "master"

            if self.kind != "master":
                self.output.clear()
                for label, value in self._destinations():
                    self.output.addItem(label, value)
                self._set_combo_value(dest)
                self.insert_summary.setText(f"Inserts: {len(self.engine.get_inserts(self.channel_id))}")

                self.send_dest.blockSignals(True)
                self.send_dest.clear()
                for label, value in self._destinations():
                    if value != "master":
                        self.send_dest.addItem(label, value)
                self.send_dest.blockSignals(False)

                sends = self.engine.get_sends(self.channel_id)
                selected = self.send_select.currentData()
                self.send_select.blockSignals(True)
                self.send_select.clear()
                for send_dest in sends:
                    self.send_select.addItem(str(send_dest), send_dest)
                if selected in sends:
                    self._set_combo_value(selected, combo=self.send_select)
                self.send_select.blockSignals(False)
                self.send_summary.setText(f"Sends: {len(sends)}")
                self.send_level.setEnabled(bool(sends))
                self.remove_send_button.setEnabled(bool(sends))
                if sends:
                    self._load_send_editor()
        finally:
            self.fader.blockSignals(False)
            self.pan.blockSignals(False)
            self.mute.blockSignals(False)
            self.solo.blockSignals(False)
            self.output.blockSignals(False)

    def update_meter(self):
        self.meter.setValue(_meter_value(self.engine.get_meter(self.channel_id)))

    def clear_meter(self):
        self.meter.setValue(0)

    def _on_fader(self, value):
        if self.kind == "track":
            self.engine.set_track_volume(int(self.channel_id), value / 100.0)
        elif self.kind == "bus":
            self.engine.set_bus_volume(self.channel_id, value / 100.0)
        self.changed.emit()

    def _on_pan(self, value):
        if self.kind == "track":
            self.engine.set_track_pan(int(self.channel_id), value / 100.0)
        elif self.kind == "bus":
            self.engine.set_bus_pan(self.channel_id, value / 100.0)
        self.changed.emit()

    def _on_mute(self, checked):
        self.engine.set_track_mute(int(self.channel_id), bool(checked))
        self.changed.emit()

    def _on_solo(self, checked):
        self.engine.set_track_solo(int(self.channel_id), bool(checked))
        self.changed.emit()

    def _on_output(self):
        if self.output.currentIndex() < 0 or self.kind == "master":
            return
        dest = self.output.currentData()
        try:
            if self.kind == "track":
                self.engine.set_track_output(int(self.channel_id), dest)
            else:
                self.engine.set_bus_output(self.channel_id, dest)
        except (ValueError, RuntimeError):
            self.sync_from_engine()
            return
        self.changed.emit()

    def _add_insert(self):
        if self.kind == "master":
            return
        self.engine.add_insert(
            self.channel_id,
            {"type": self.insert_type.currentText(), "enabled": True},
        )
        self.sync_from_engine()
        self.changed.emit()

    def _clear_inserts(self):
        if self.kind == "master":
            return
        self.engine.set_inserts(self.channel_id, [])
        self.sync_from_engine()
        self.changed.emit()

    def _add_send(self):
        if self.kind == "master" or self.send_dest.currentIndex() < 0:
            return
        try:
            self.engine.add_send(
                self.channel_id,
                self.send_dest.currentData(),
                level=1.0,
                mode=self.send_mode.currentText(),
            )
        except (ValueError, RuntimeError):
            self.sync_from_engine()
            return
        self.sync_from_engine()
        self.changed.emit()

    def _load_send_editor(self):
        if self.send_select.currentIndex() < 0:
            return
        dest = self.send_select.currentData()
        self.send_level.blockSignals(True)
        self.send_mode.blockSignals(True)
        try:
            self.send_level.setValue(
                round(self.engine.get_send_level(self.channel_id, dest) * 100)
            )
            self.send_mode.setCurrentText(
                self.engine.get_send_mode(self.channel_id, dest)
            )
        finally:
            self.send_level.blockSignals(False)
            self.send_mode.blockSignals(False)

    def _set_send_level(self, value):
        if self.send_select.currentIndex() < 0:
            return
        self.engine.set_send_level(
            self.channel_id, self.send_select.currentData(), value / 100.0
        )
        self.changed.emit()

    def _set_send_mode(self, mode):
        if self.send_select.currentIndex() < 0:
            return
        try:
            self.engine.set_send_mode(
                self.channel_id, self.send_select.currentData(), mode
            )
        except (ValueError, RuntimeError):
            self.sync_from_engine()
            return
        self.changed.emit()

    def _remove_send(self):
        if self.send_select.currentIndex() < 0:
            return
        self.engine.remove_send(self.channel_id, self.send_select.currentData())
        self.sync_from_engine()
        self.changed.emit()


class MixerWidget(QWidget):
    """Horizontally scrolling mixer built directly from live engine state."""

    changed = pyqtSignal()

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.track_names = {}
        self.strips = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        title = QLabel("Mixer")
        title.setStyleSheet("font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.rebuild)
        header.addWidget(self.refresh_button)
        root.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.channel_layout = QHBoxLayout(self.container)
        self.channel_layout.setContentsMargins(6, 6, 6, 6)
        self.channel_layout.setSpacing(6)
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)

        self.rebuild()

    def set_track_names(self, names):
        self.track_names = {int(k): str(v) for k, v in (names or {}).items()}
        self.rebuild()

    def _track_ids(self):
        ids = set(self.track_names)
        for attr in ("track_volumes", "track_pans", "track_mutes", "track_solos", "track_outputs"):
            for key in (getattr(self.engine, attr, {}) or {}):
                try:
                    ids.add(int(key))
                except (TypeError, ValueError):
                    pass
        return sorted(ids)

    def rebuild(self):
        while self.channel_layout.count():
            item = self.channel_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.strips = {}

        for tid in self._track_ids():
            name = self.track_names.get(tid, f"Track {tid + 1}")
            strip = MixerChannelStrip(tid, name, self.engine, "track")
            strip.changed.connect(self.changed)
            self.channel_layout.addWidget(strip)
            self.strips[("track", tid)] = strip

        for bus in self.engine.list_buses():
            strip = MixerChannelStrip(bus, bus, self.engine, "bus")
            strip.changed.connect(self.changed)
            self.channel_layout.addWidget(strip)
            self.strips[("bus", bus)] = strip

        master = MixerChannelStrip("master", "Master", self.engine, "master")
        self.channel_layout.addWidget(master)
        self.strips[("master", "master")] = master
        self.channel_layout.addStretch()

    def sync_from_engine(self):
        expected_tracks = set(self._track_ids())
        expected_buses = set(self.engine.list_buses())
        shown_tracks = {k[1] for k in self.strips if k[0] == "track"}
        shown_buses = {k[1] for k in self.strips if k[0] == "bus"}
        if expected_tracks != shown_tracks or expected_buses != shown_buses:
            self.rebuild()
            return
        for strip in self.strips.values():
            strip.sync_from_engine()

    def update_meters(self):
        for strip in self.strips.values():
            strip.update_meter()

    def clear_meters(self):
        for strip in self.strips.values():
            strip.clear_meter()
