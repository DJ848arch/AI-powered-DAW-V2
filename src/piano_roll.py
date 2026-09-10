"""Lightweight piano-roll: pitch vs start_beat, click to add a note."""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QMouseEvent


_PITCH_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_BLACK_PC = {1, 3, 6, 8, 10}


class PianoRoll(QWidget):
    """Shows MidiClip.notes as pitch vs start_beat. Click adds a 1-beat note."""

    note_added = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.clip = None
        self.min_pitch = 36
        self.max_pitch = 84
        self.beats_visible = 16.0
        self.beat_width = 36.0
        self.key_height = 12.0
        self.label_width = 40.0
        self.setMinimumHeight(180)
        self.setMinimumWidth(360)
        self.setMouseTracking(False)
        self.setStyleSheet("background: #1e1e22;")

        rows = self.max_pitch - self.min_pitch + 1
        self.setMinimumHeight(int(rows * self.key_height * 0.4))

    def set_clip(self, clip):
        """Bind the MidiClip this roll edits."""
        self.clip = clip
        self.update()

    def _rows(self) -> int:
        return self.max_pitch - self.min_pitch + 1

    def _pitch_at_y(self, y: float) -> int:
        row = int(y / self.key_height)
        pitch = self.max_pitch - row
        return max(self.min_pitch, min(self.max_pitch, pitch))

    def _y_for_pitch(self, pitch: int) -> float:
        return (self.max_pitch - pitch) * self.key_height

    def _beat_at_x(self, x: float) -> float:
        beat = (x - self.label_width) / self.beat_width
        beat = max(0.0, beat)
        return round(beat * 4.0) / 4.0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(30, 30, 34))

        rows = self._rows()
        width = self.width()
        font = QFont("Sans Serif", 8)
        painter.setFont(font)

        for row in range(rows + 1):
            pitch = self.max_pitch - row
            y = row * self.key_height
            pc = pitch % 12
            lane = QColor(28, 28, 32) if pc in _BLACK_PC else QColor(38, 38, 44)
            painter.fillRect(
                QRectF(self.label_width, y, width - self.label_width, self.key_height),
                lane,
            )
            painter.fillRect(
                QRectF(0, y, self.label_width, self.key_height),
                QColor(22, 22, 26) if pc in _BLACK_PC else QColor(48, 48, 54),
            )
            if pc == 0:
                painter.setPen(QColor(200, 200, 200))
                octave = pitch // 12 - 1
                painter.drawText(
                    QRectF(2, y, self.label_width - 4, self.key_height),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    f"C{octave}",
                )
            painter.setPen(QPen(QColor(55, 55, 62), 1))
            painter.drawLine(0, int(y), width, int(y))

        beats = int(self.beats_visible) + 1
        for beat in range(beats):
            x = self.label_width + beat * self.beat_width
            bar = beat % 4 == 0
            painter.setPen(QPen(QColor(80, 80, 90) if bar else QColor(50, 50, 56), 1))
            painter.drawLine(int(x), 0, int(x), int(rows * self.key_height))

        if self.clip is not None:
            painter.setPen(QPen(QColor(30, 80, 140), 1))
            for note in self.clip.notes:
                pitch = int(getattr(note, "pitch", 60))
                if pitch < self.min_pitch or pitch > self.max_pitch:
                    continue
                start = float(getattr(note, "start_beat", 0.0))
                dur = float(getattr(note, "duration_beats", 1.0))
                x = self.label_width + start * self.beat_width
                y = self._y_for_pitch(pitch)
                w = max(6.0, dur * self.beat_width - 1.0)
                painter.fillRect(
                    QRectF(x + 1, y + 1, w, self.key_height - 2),
                    QColor(90, 160, 230),
                )

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.clip is None:
            return
        pos = event.position()
        if pos.x() < self.label_width:
            return
        pitch = self._pitch_at_y(pos.y())
        start_beat = self._beat_at_x(pos.x())
        note = self.clip.add_note(pitch, start_beat, 1.0, 100)
        self.note_added.emit(note)
        self.update()


PianoRollWidget = PianoRoll
