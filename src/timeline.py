"""
Multi-track Timeline Widget
Provides zoom, scroll, selection, and waveform visualization
"""

import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QFrame, QLabel, QMenu, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QMouseEvent

from clip import AudioClip, ClipManager


class TimelineWidget(QWidget):
    """Multi-track timeline with waveform visualization"""
    
    # Signals
    clip_selected = pyqtSignal(object)
    playhead_moved = pyqtSignal(float)
    selection_changed = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.tracks = {}  # track_id: TrackData
        self.clips = {}  # clip_id: AudioClip
        self.selected_clips = set()
        self.clip_manager = ClipManager()
        
        # Timeline settings
        self.pixels_per_second = 50
        self.track_height = 80
        self.header_height = 30
        self.zoom_level = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 10.0
        
        # Playback
        self.playhead_position = 0.0  # seconds
        self.is_playing = False
        self.bpm = 120
        self.sample_rate = 44100
        
        # Interaction
        self.dragging = False
        self.drag_start = None
        self.selection_rect = None
        self.resizing_clip = None
        self.moving_clip = None
        self.clip_offset = None
        
        # Colors
        self.colors = {
            'background': QColor(40, 40, 45),
            'track_bg': QColor(50, 50, 55),
            'track_alt': QColor(45, 45, 50),
            'grid': QColor(70, 70, 75),
            'playhead': QColor(255, 200, 0),
            'selection': QColor(100, 150, 255, 100),
            'clip_border': QColor(100, 100, 110),
            'clip_selected': QColor(100, 150, 255),
            'waveform': QColor(100, 200, 255),
            'waveform_bg': QColor(60, 60, 65),
            'text': QColor(200, 200, 200)
        }
        
        self._setup_ui()
        self._start_playback_timer()
        
    def _setup_ui(self):
        """Set up the UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Timeline ruler
        self.ruler = TimelineRuler(self)
        self.ruler.setFixedHeight(self.header_height)
        layout.addWidget(self.ruler)
        
        # Scroll area for tracks
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        
        # Track container
        self.track_container = TrackContainer(self)
        self.scroll_area.setWidget(self.track_container)
        
        layout.addWidget(self.scroll_area)
        
        # Set minimum size
        self.setMinimumWidth(800)
        self.setMinimumHeight(400)
        
    def _start_playback_timer(self):
        """Start the playback update timer"""
        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self._update_playhead)
        self.playback_timer.setInterval(50)  # 20 FPS
        
    def _update_playhead(self):
        """Update playhead position during playback"""
        if self.is_playing:
            self.playhead_position += 0.05  # 50ms increments
            self.ruler.update()
            self.track_container.update()
            self.playhead_moved.emit(self.playhead_position)
            
    def paintEvent(self, event):
        """Paint the timeline background"""
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.colors['background'])
        painter.end()
        
    def add_track(self, track_id, name="New Track"):
        """Add a new track to the timeline"""
        self.tracks[track_id] = {
            'id': track_id,
            'name': name,
            'clips': [],
            'muted': False,
            'solo': False,
            'height': self.track_height
        }
        self.track_container.update_tracks()
        
    def remove_track(self, track_id):
        """Remove a track from the timeline"""
        if track_id in self.tracks:
            # Remove all clips on this track
            for clip_id in self.tracks[track_id]['clips']:
                if clip_id in self.clips:
                    del self.clips[clip_id]
            del self.tracks[track_id]
            self.track_container.update_tracks()
            
    def add_clip(self, track_id, clip: AudioClip, position: float):
        """Add a clip to a track at a specific position"""
        if track_id not in self.tracks:
            return
            
        clip.track_id = track_id
        clip.start_time = position
        self.clips[clip.id] = clip
        self.tracks[track_id]['clips'].append(clip.id)
        self.track_container.update()
        
    def remove_clip(self, clip_id):
        """Remove a clip from the timeline"""
        if clip_id in self.clips:
            clip = self.clips[clip_id]
            if clip.track_id in self.tracks:
                self.tracks[clip.track_id]['clips'].remove(clip_id)
            del self.clips[clip_id]
            self.selected_clips.discard(clip_id)
        self.track_container.update()
        
    def zoom_in(self):
        """Zoom in on the timeline"""
        if self.zoom_level < self.max_zoom:
            self.zoom_level *= 1.2
            self.pixels_per_second = int(50 * self.zoom_level)
            self.ruler.update()
            self.track_container.update()
            
    def zoom_out(self):
        """Zoom out on the timeline"""
        if self.zoom_level > self.min_zoom:
            self.zoom_level /= 1.2
            self.pixels_per_second = int(50 * self.zoom_level)
            self.ruler.update()
            self.track_container.update()
            
    def zoom_to_fit(self):
        """Zoom to fit all content"""
        if not self.clips:
            self.zoom_level = 1.0
        else:
            max_time = max(clip.end_time for clip in self.clips.values())
            if max_time > 0:
                self.zoom_level = max(self.min_zoom, 
                                     min(self.max_zoom, 
                                         self.width() / (max_time * 50)))
                self.pixels_per_second = int(50 * self.zoom_level)
        self.ruler.update()
        self.track_container.update()
        
    def start_playback(self):
        """Start playback"""
        self.is_playing = True
        self.playback_timer.start()
        
    def pause_playback(self):
        """Pause playback"""
        self.is_playing = False
        self.playback_timer.stop()
        
    def stop_playback(self):
        """Stop playback and reset to beginning"""
        self.is_playing = False
        self.playback_timer.stop()
        self.playhead_position = 0.0
        self.ruler.update()
        self.track_container.update()
        
    def set_playhead(self, position: float):
        """Set playhead position in seconds"""
        self.playhead_position = max(0, position)
        self.ruler.update()
        self.track_container.update()
        
    def set_bpm(self, bpm: int):
        """Set the BPM"""
        self.bpm = bpm
        self.ruler.update()
        
    def cut_selected(self):
        """Cut selected clips"""
        for clip_id in list(self.selected_clips):
            if clip_id in self.clips:
                self.clip_manager.cut_clip(self.clips[clip_id], self.playhead_position)
        self.track_container.update()
        
    def copy_selected(self):
        """Copy selected clips to clipboard"""
        self.clip_manager.clipboard = [
            self.clips[clip_id] for clip_id in self.selected_clips 
            if clip_id in self.clips
        ]
        
    def paste(self):
        """Paste clips from clipboard"""
        for clip in self.clip_manager.clipboard:
            new_clip = clip.copy()
            new_clip.start_time = self.playhead_position
            self.add_clip(clip.track_id, new_clip, self.playhead_position)
        self.track_container.update()
        
    def delete_selected(self):
        """Delete selected clips"""
        for clip_id in list(self.selected_clips):
            self.remove_clip(clip_id)
        self.selected_clips.clear()
        self.selection_changed.emit([])
        
    def select_clip(self, clip_id, add_to_selection=False):
        """Select a clip"""
        if not add_to_selection:
            self.selected_clips.clear()
        if clip_id:
            self.selected_clips.add(clip_id)
        self.clip_selected.emit(self.clips.get(clip_id))
        self.selection_changed.emit(list(self.selected_clips))
        self.track_container.update()
        
    def clear(self):
        """Clear all tracks and clips"""
        self.tracks.clear()
        self.clips.clear()
        self.selected_clips.clear()
        self.playhead_position = 0.0
        self.is_playing = False
        self.track_container.update_tracks()
        
    def get_state(self):
        """Get timeline state for saving"""
        return {
            'tracks': self.tracks,
            'clips': {k: v.to_dict() for k, v in self.clips.items()},
            'zoom_level': self.zoom_level,
            'bpm': self.bpm
        }
        
    def set_state(self, state):
        """Set timeline state from loaded project"""
        self.clear()
        if 'tracks' in state:
            self.tracks = state['tracks']
        if 'clips' in state:
            for clip_id, clip_data in state['clips'].items():
                self.clips[clip_id] = AudioClip.from_dict(clip_data)
        if 'zoom_level' in state:
            self.zoom_level = state['zoom_level']
            self.pixels_per_second = int(50 * self.zoom_level)
        if 'bpm' in state:
            self.bpm = state['bpm']
        self.track_container.update_tracks()


class TimelineRuler(QWidget):
    """Timeline ruler with time markers"""
    
    def __init__(self, timeline: TimelineWidget):
        super().__init__(timeline)
        self.timeline = timeline
        
    def paintEvent(self, event):
        painter = QPainter(self)
        
        # Background
        painter.fillRect(self.rect(), self.timeline.colors['background'])
        
        # Draw border
        pen = QPen(self.timeline.colors['grid'])
        painter.setPen(pen)
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        
        # Draw time markers
        painter.setPen(self.timeline.colors['text'])
        font = QFont("Arial", 9)
        painter.setFont(font)
        
        pixels_per_second = self.timeline.pixels_per_second
        
        # Determine marker interval based on zoom
        if pixels_per_second >= 200:
            interval = 0.5  # 0.5 seconds
        elif pixels_per_second >= 100:
            interval = 1.0  # 1 second
        elif pixels_per_second >= 50:
            interval = 2.0  # 2 seconds
        elif pixels_per_second >= 25:
            interval = 5.0  # 5 seconds
        else:
            interval = 10.0  # 10 seconds
            
        # Draw markers
        max_time = self.width() / pixels_per_second
        t = 0
        while t <= max_time:
            x = int(t * pixels_per_second)
            
            # Major marker
            painter.drawLine(x, self.height() - 15, x, self.height())
            
            # Time label
            minutes = int(t // 60)
            seconds = int(t % 60)
            if interval < 1:
                millis = int((t % 1) * 1000)
                label = f"{minutes}:{seconds:02d}.{millis:03d}"
            else:
                label = f"{minutes}:{seconds:02d}"
            painter.drawText(x + 2, 12, label)
            
            t += interval
            
        # Draw playhead position
        playhead_x = int(self.timeline.playhead_position * pixels_per_second)
        if 0 <= playhead_x <= self.width():
            painter.setPen(QPen(self.timeline.colors['playhead'], 2))
            painter.drawLine(playhead_x, 0, playhead_x, self.height())
            
        painter.end()


class TrackContainer(QWidget):
    """Container for track lanes"""
    
    def __init__(self, timeline: TimelineWidget):
        super().__init__(timeline)
        self.timeline = timeline
        self.setMinimumWidth(2000)
        
    def update_tracks(self):
        """Update track layout"""
        total_height = len(self.timeline.tracks) * self.timeline.track_height
        self.setMinimumHeight(max(total_height, 400))
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        
        # Calculate dimensions
        pixels_per_second = self.timeline.pixels_per_second
        track_height = self.timeline.track_height
        
        # Draw track backgrounds
        y = 0
        for i, (track_id, track) in enumerate(self.timeline.tracks.items()):
            # Alternate track colors
            if i % 2 == 0:
                color = self.timeline.colors['track_bg']
            else:
                color = self.timeline.colors['track_alt']
                
            # Draw track background
            painter.fillRect(0, y, self.width(), track_height, color)
            
            # Draw track border
            painter.setPen(self.timeline.colors['grid'])
            painter.drawLine(0, y + track_height, self.width(), y + track_height)
            
            # Draw clips on this track
            for clip_id in track['clips']:
                if clip_id in self.timeline.clips:
                    clip = self.timeline.clips[clip_id]
                    self._draw_clip(painter, clip, y, track_height, pixels_per_second)
                    
            y += track_height
            
        # Draw grid lines
        self._draw_grid(painter, pixels_per_second)
        
        # Draw playhead
        playhead_x = int(self.timeline.playhead_position * pixels_per_second)
        if 0 <= playhead_x <= self.width():
            painter.setPen(QPen(self.timeline.colors['playhead'], 2))
            painter.drawLine(playhead_x, 0, playhead_x, self.height())
            
        # Draw selection rectangle
        if self.timeline.selection_rect:
            painter.setPen(QPen(self.timeline.colors['selection'], 1, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(self.timeline.colors['selection']))
            painter.drawRect(self.timeline.selection_rect)
            
        painter.end()
        
    def _draw_clip(self, painter, clip: AudioClip, y: int, height: int, pps: int):
        """Draw an audio clip with waveform"""
        x = int(clip.start_time * pps)
        width = int(clip.duration * pps)
        
        # Clip background
        is_selected = clip.id in self.timeline.selected_clips
        if is_selected:
            painter.setPen(QPen(self.timeline.colors['clip_selected'], 2))
            bg_color = QColor(70, 70, 80)
        else:
            painter.setPen(QPen(self.timeline.colors['clip_border'], 1))
            bg_color = self.timeline.colors['waveform_bg']
            
        painter.fillRect(x, y + 2, width, height - 4, bg_color)
        painter.drawRect(x, y + 2, width, height - 4)
        
        # Draw waveform if available
        if clip.waveform_data is not None and len(clip.waveform_data) > 0:
            self._draw_waveform(painter, clip, x, y + 5, width, height - 10)
            
        # Clip name
        painter.setPen(self.timeline.colors['text'])
        font = QFont("Arial", 8)
        painter.setFont(font)
        painter.drawText(x + 4, y + 15, clip.name[:20])
        
    def _draw_waveform(self, painter, clip: AudioClip, x: int, y: int, width: int, height: int):
        """Draw waveform visualization"""
        if clip.waveform_data is None or len(clip.waveform_data) == 0:
            return
            
        # Calculate samples per pixel
        samples = clip.waveform_data
        samples_per_pixel = max(1, len(samples) // width)
        
        painter.setPen(self.timeline.colors['waveform'])
        
        center_y = y + height // 2
        max_amplitude = np.max(np.abs(samples)) if len(samples) > 0 else 1.0
        
        if max_amplitude == 0:
            max_amplitude = 1.0
            
        # Draw waveform
        for i in range(width):
            start_idx = i * samples_per_pixel
            end_idx = min(start_idx + samples_per_pixel, len(samples))
            
            if start_idx < len(samples):
                chunk = samples[start_idx:end_idx]
                min_val = np.min(chunk)
                max_val = np.max(chunk)
                
                # Scale to pixel height
                min_y = center_y + int((min_val / max_amplitude) * (height // 2))
                max_y = center_y + int((max_val / max_amplitude) * (height // 2))
                
                painter.drawLine(x + i, min_y, x + i, max_y)
                
    def _draw_grid(self, painter, pps: int):
        """Draw grid lines"""
        painter.setPen(QPen(self.timeline.colors['grid'], 1, Qt.PenStyle.DotLine))
        
        # Determine grid interval
        if pps >= 200:
            interval = 0.25
        elif pps >= 100:
            interval = 0.5
        elif pps >= 50:
            interval = 1.0
        else:
            interval = 2.0
            
        max_time = self.width() / pps
        t = 0
        while t <= max_time:
            x = int(t * pps)
            painter.drawLine(x, 0, x, self.height())
            t += interval
            
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press"""
        pos = event.pos()
        pixels_per_second = self.timeline.pixels_per_second
        
        # Check if clicking on a clip
        clicked_clip = self._get_clip_at(pos)
        
        if event.button() == Qt.MouseButton.LeftButton:
            if clicked_clip:
                # Select clip
                add_to_selection = event.modifiers() == Qt.KeyboardModifier.ControlModifier
                self.timeline.select_clip(clicked_clip.id, add_to_selection)
                self.timeline.moving_clip = clicked_clip
                self.timeline.clip_offset = pos.x() - int(clicked_clip.start_time * pixels_per_second)
            else:
                # Start selection
                self.timeline.dragging = True
                self.timeline.drag_start = pos
                self.timeline.selection_rect = QRect(pos, pos)
                if event.modifiers() != Qt.KeyboardModifier.ControlModifier:
                    self.timeline.selected_clips.clear()
                    
        elif event.button() == Qt.MouseButton.RightButton:
            # Context menu
            self._show_context_menu(event.globalPosition().toPoint(), clicked_clip)
            
        self.update()
        
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move"""
        pos = event.pos()
        
        if self.timeline.dragging and self.timeline.drag_start:
            # Update selection rectangle
            self.timeline.selection_rect = QRect(
                self.timeline.drag_start, pos
            ).normalized()
            
            # Select clips in rectangle
            self._select_clips_in_rect(self.timeline.selection_rect)
            
        elif self.timeline.moving_clip:
            # Move clip
            pixels_per_second = self.timeline.pixels_per_second
            new_x = pos.x() - self.timeline.clip_offset
            new_time = max(0, new_x / pixels_per_second)
            self.timeline.moving_clip.start_time = new_time
            
        self.update()
        
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release"""
        if self.timeline.dragging:
            self.timeline.dragging = False
            self.timeline.drag_start = None
            self.timeline.selection_rect = None
            
        if self.timeline.moving_clip:
            self.timeline.moving_clip = None
            self.timeline.clip_offset = None
            
        self.update()
        
    def _get_clip_at(self, pos: QPoint) -> AudioClip:
        """Get clip at position"""
        pixels_per_second = self.timeline.pixels_per_second
        track_height = self.timeline.track_height
        
        track_idx = pos.y() // track_height
        track_ids = list(self.timeline.tracks.keys())
        
        if track_idx >= len(track_ids):
            return None
            
        track_id = track_ids[track_idx]
        time = pos.x() / pixels_per_second
        
        for clip_id in self.timeline.tracks[track_id]['clips']:
            if clip_id in self.timeline.clips:
                clip = self.timeline.clips[clip_id]
                if clip.start_time <= time <= clip.end_time:
                    return clip
                    
        return None
        
    def _select_clips_in_rect(self, rect: QRect):
        """Select clips within rectangle"""
        pixels_per_second = self.timeline.pixels_per_second
        track_height = self.timeline.track_height
        
        for clip_id, clip in self.timeline.clips.items():
            clip_x = int(clip.start_time * pixels_per_second)
            clip_width = int(clip.duration * pixels_per_second)
            clip_track_idx = list(self.timeline.tracks.keys()).index(clip.track_id)
            clip_y = clip_track_idx * track_height
            
            clip_rect = QRect(clip_x, clip_y, clip_width, track_height)
            
            if rect.intersects(clip_rect):
                self.timeline.selected_clips.add(clip_id)
                
    def _show_context_menu(self, pos, clip: AudioClip):
        """Show context menu"""
        menu = QMenu(self)
        
        if clip:
            menu.addAction("Cut", self.timeline.cut_selected)
            menu.addAction("Copy", self.timeline.copy_selected)
            menu.addSeparator()
            menu.addAction("Delete", self.timeline.delete_selected)
            menu.addSeparator()
            menu.addAction("Properties", lambda: self._show_clip_properties(clip))
        else:
            menu.addAction("Paste", self.timeline.paste)
            menu.addSeparator()
            menu.addAction("Import Audio...", self._import_audio)
            
        menu.exec(pos)
        
    def _show_clip_properties(self, clip: AudioClip):
        """Show clip properties dialog"""
        QMessageBox.information(
            self, "Clip Properties",
            f"Name: {clip.name}\n"
            f"Duration: {clip.duration:.3f}s\n"
            f"Sample Rate: {clip.sample_rate} Hz\n"
            f"Channels: {clip.channels}"
        )
        
    def _import_audio(self):
        """Import audio file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Audio", "",
            "Audio Files (*.wav *.mp3 *.flac *.ogg);;All Files (*)"
        )
        
        if file_path:
            # Determine which track to add to
            # For now, add to first track or create one
            if not self.timeline.tracks:
                self.timeline.add_track(0, "Track 1")
                
            track_id = list(self.timeline.tracks.keys())[0]
            
            try:
                clip = AudioClip.from_file(file_path)
                self.timeline.add_clip(track_id, clip, self.timeline.playhead_position)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import audio: {str(e)}")
