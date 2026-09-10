"""
AI-Integrated DAW - Main Application Window
Digital Audio Workstation with AI agent integration
"""

import sys
import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QMenuBar, QToolBar, QStatusBar, QFileDialog,
    QMessageBox, QSplitter, QDockWidget, QApplication,
    QLabel, QPushButton, QSpinBox, QComboBox, QFrame
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QKeySequence

from timeline import TimelineWidget
from track_panel import TrackPanel
from transport_controls import TransportControls
from chat_widget import ChatWidget
from project import ProjectManager
from audio_engine import AudioEngine
from midi_clip import MidiClip, MidiNote
from piano_roll import PianoRoll
from agent_manager import AgentManager
import midi_synth


class MainWindow(QMainWindow):
    """Main application window for the AI-Integrated DAW"""
    
    # Signals
    project_loaded = pyqtSignal(str)
    project_saved = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.project_manager = ProjectManager()
        self.current_project_path = None
        self.is_modified = False
        self.audio_engine = AudioEngine()
        self.audio_engine.initialize()
        self.midi_clips: list[MidiClip] = []
        self.agent_manager = AgentManager()
        self._applied_track_session = None
        
        self.setWindowTitle("AI-Integrated DAW")
        self.setGeometry(100, 100, 1400, 900)
        
        self._setup_ui()
        self._create_actions()
        self._create_menus()
        self._create_toolbars()
        self._create_statusbar()
        self._create_dock_widgets()
        
        # Set up auto-save timer
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self._autosave)
        self.autosave_timer.start(60000)  # Auto-save every minute
        
    def _setup_ui(self):
        """Set up the central widget and main layout"""
        # Central widget with splitter
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Transport controls at top
        self.transport = TransportControls()
        main_layout.addWidget(self.transport)
        
        # Main splitter (timeline + track panel)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Track panel on left
        self.track_panel = TrackPanel()
        self.track_panel.set_engine(self.audio_engine)
        self.main_splitter.addWidget(self.track_panel)
        
        # Timeline in center
        self.timeline = TimelineWidget()
        self.main_splitter.addWidget(self.timeline)
        
        # Set splitter proportions
        self.main_splitter.setSizes([250, 1150])
        
        main_layout.addWidget(self.main_splitter, 1)
        
        # Connect signals
        self.transport.play_clicked.connect(self._on_play)
        self.transport.pause_clicked.connect(self._on_pause)
        self.transport.stop_clicked.connect(self._on_stop)
        self.transport.record_clicked.connect(self._on_record)
        self.transport.bpm_changed.connect(self._on_bpm_changed)
        self.audio_engine.playback_position_changed.connect(self._on_playback_position)
        self.audio_engine.playback_finished.connect(self._on_engine_finished)
        self.audio_engine.error_occurred.connect(self._on_engine_error)
        self.track_panel.track_selected.connect(self._on_track_selected)
        self.track_panel.output_changed.connect(self._on_track_output_changed)
        
    def _create_actions(self):
        """Create all application actions"""
        # File actions
        self.new_action = QAction("&New Project", self)
        self.new_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_action.setStatusTip("Create a new project")
        self.new_action.triggered.connect(self._new_project)
        
        self.open_action = QAction("&Open Project...", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.setStatusTip("Open an existing project")
        self.open_action.triggered.connect(self._open_project)
        
        self.save_action = QAction("&Save Project", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.setStatusTip("Save the current project")
        self.save_action.triggered.connect(self._save_project)
        
        self.save_as_action = QAction("Save Project &As...", self)
        self.save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.save_as_action.setStatusTip("Save project with a new name")
        self.save_as_action.triggered.connect(self._save_project_as)
        
        self.export_action = QAction("&Export Audio...", self)
        self.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_action.setStatusTip("Export project to audio file")
        self.export_action.triggered.connect(self._export_audio)
        
        self.exit_action = QAction("E&xit", self)
        self.exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.exit_action.setStatusTip("Exit the application")
        self.exit_action.triggered.connect(self.close)
        
        # Edit actions
        self.undo_action = QAction("&Undo", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self._undo)
        
        self.redo_action = QAction("&Redo", self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self._redo)
        
        self.cut_action = QAction("Cu&t", self)
        self.cut_action.setShortcut(QKeySequence.StandardKey.Cut)
        self.cut_action.triggered.connect(self._cut)
        
        self.copy_action = QAction("&Copy", self)
        self.copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        self.copy_action.triggered.connect(self._copy)
        
        self.paste_action = QAction("&Paste", self)
        self.paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        self.paste_action.triggered.connect(self._paste)
        
        self.delete_action = QAction("&Delete", self)
        self.delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.delete_action.triggered.connect(self._delete)
        
        # Track actions
        self.add_track_action = QAction("&Add Track", self)
        self.add_track_action.setShortcut(QKeySequence("Ctrl+T"))
        self.add_track_action.triggered.connect(self._add_track)
        
        self.remove_track_action = QAction("&Remove Track", self)
        self.remove_track_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        self.remove_track_action.triggered.connect(self._remove_track)
        
        # View actions
        self.zoom_in_action = QAction("Zoom &In", self)
        self.zoom_in_action.setShortcut(QKeySequence("Ctrl++"))
        self.zoom_in_action.triggered.connect(self._zoom_in)
        
        self.zoom_out_action = QAction("Zoom &Out", self)
        self.zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        self.zoom_out_action.triggered.connect(self._zoom_out)
        
        self.zoom_fit_action = QAction("Zoom to &Fit", self)
        self.zoom_fit_action.setShortcut(QKeySequence("Ctrl+0"))
        self.zoom_fit_action.triggered.connect(self._zoom_fit)
        
        # AI Agent actions
        self.open_chat_action = QAction("Open AI &Chat", self)
        self.open_chat_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self.open_chat_action.triggered.connect(self._toggle_chat)
        
        self.generate_music_action = QAction("&Generate Music...", self)
        self.generate_music_action.setShortcut(QKeySequence("Ctrl+G"))
        self.generate_music_action.triggered.connect(self._generate_music)
        
    def _create_menus(self):
        """Create menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)
        
        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.cut_action)
        edit_menu.addAction(self.copy_action)
        edit_menu.addAction(self.paste_action)
        edit_menu.addAction(self.delete_action)
        
        # Track menu
        track_menu = menubar.addMenu("&Track")
        track_menu.addAction(self.add_track_action)
        track_menu.addAction(self.remove_track_action)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addAction(self.zoom_fit_action)
        
        # AI Agent menu
        ai_menu = menubar.addMenu("&AI Agent")
        ai_menu.addAction(self.open_chat_action)
        ai_menu.addAction(self.generate_music_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
        
    def _create_toolbars(self):
        """Create toolbars"""
        # Main toolbar
        self.main_toolbar = QToolBar("Main Toolbar", self)
        self.main_toolbar.setMovable(False)
        self.addToolBar(self.main_toolbar)
        
        self.main_toolbar.addAction(self.new_action)
        self.main_toolbar.addAction(self.open_action)
        self.main_toolbar.addAction(self.save_action)
        self.main_toolbar.addSeparator()
        self.main_toolbar.addAction(self.cut_action)
        self.main_toolbar.addAction(self.copy_action)
        self.main_toolbar.addAction(self.paste_action)
        self.main_toolbar.addSeparator()
        self.main_toolbar.addAction(self.zoom_in_action)
        self.main_toolbar.addAction(self.zoom_out_action)
        self.main_toolbar.addSeparator()
        self.main_toolbar.addAction(self.open_chat_action)
        
        # Edit toolbar
        self.edit_toolbar = QToolBar("Edit Toolbar", self)
        self.edit_toolbar.setMovable(True)
        self.addToolBar(self.edit_toolbar)
        
        self.edit_toolbar.addAction(self.add_track_action)
        self.edit_toolbar.addAction(self.remove_track_action)
        self.edit_toolbar.addSeparator()
        self.edit_toolbar.addAction(self.generate_music_action)
        
    def _create_statusbar(self):
        """Create status bar"""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        
        # Status labels
        self.status_label = QLabel("Ready")
        self.statusbar.addWidget(self.status_label)
        
        self.position_label = QLabel("00:00:00.000")
        self.statusbar.addPermanentWidget(self.position_label)
        
        self.sample_rate_label = QLabel("44.1 kHz")
        self.statusbar.addPermanentWidget(self.sample_rate_label)
        
        self.project_status_label = QLabel("No Project")
        self.statusbar.addPermanentWidget(self.project_status_label)
        
    def _create_dock_widgets(self):
        """Create dockable widgets"""
        # AI Chat dock
        self.chat_dock = QDockWidget("AI Assistant", self)
        self.chat_widget = ChatWidget()
        self.chat_dock.setWidget(self.chat_widget)
        self.chat_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | 
            Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.chat_dock)
        self.chat_dock.hide()

        self.piano_roll = PianoRoll()
        self.piano_roll_dock = QDockWidget("Piano Roll", self)
        self.piano_roll_dock.setWidget(self.piano_roll)
        self.piano_roll_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea |
            Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.piano_roll_dock)
        self.piano_roll.set_clip(self._clip_for_selected_track())
        self.piano_roll.note_added.connect(self._on_midi_note_added)
        self.chat_widget.set_agent_manager(self.agent_manager)
        self.chat_widget.stage_approved.connect(self._on_stage_approved)
        self.agent_manager.production_complete.connect(self._on_agent_production_complete)
        
    # ===== Action Handlers =====
    
    def _new_project(self):
        """Create a new project"""
        if self._check_save():
            self.project_manager.new_project()
            self.timeline.clear()
            self.track_panel.clear()
            self.midi_clips = []
            self._applied_track_session = None
            self.piano_roll.set_clip(self._clip_for_selected_track())
            self.current_project_path = None
            self.is_modified = False
            self._update_title()
            self.status_label.setText("New project created")
            
    def _open_project(self):
        """Open an existing project"""
        if not self._check_save():
            return
            
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "DAW Projects (*.daw);;All Files (*)"
        )
        
        if file_path:
            try:
                project_data = self.project_manager.load_project(
                    file_path, engine=self.audio_engine
                )
                self._load_project_data(project_data)
                self.current_project_path = file_path
                self.is_modified = False
                self._update_title()
                self.project_loaded.emit(file_path)
                self.status_label.setText(f"Opened: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open project: {str(e)}")
                
    def _save_project(self):
        """Save current project"""
        if self.current_project_path:
            self._do_save(self.current_project_path)
        else:
            self._save_project_as()
            
    def _save_project_as(self):
        """Save project with new name"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "", "DAW Projects (*.daw);;All Files (*)"
        )
        
        if file_path:
            self._do_save(file_path)
            
    def _do_save(self, file_path):
        """Perform the actual save operation"""
        try:
            project_data = self._get_project_data()
            self.project_manager.save_project(
                file_path, project_data, engine=self.audio_engine
            )
            self.current_project_path = file_path
            self.is_modified = False
            self._update_title()
            self.project_saved.emit(file_path)
            self.status_label.setText(f"Saved: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save project: {str(e)}")
            
    def _export_audio(self):
        """Export project to audio file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Audio", "", 
            "WAV Files (*.wav);;MP3 Files (*.mp3);;FLAC Files (*.flac);;All Files (*)"
        )
        
        if file_path:
            self.status_label.setText(f"Exporting to: {file_path}")
            # Export logic would go here
            QMessageBox.information(self, "Export", f"Audio exported to: {file_path}")
            
    def _undo(self):
        """Undo last action"""
        self.status_label.setText("Undo")
        
    def _redo(self):
        """Redo last undone action"""
        self.status_label.setText("Redo")
        
    def _cut(self):
        """Cut selected"""
        self.timeline.cut_selected()
        self.is_modified = True
        
    def _copy(self):
        """Copy selected"""
        self.timeline.copy_selected()
        
    def _paste(self):
        """Paste from clipboard"""
        self.timeline.paste()
        self.is_modified = True
        
    def _delete(self):
        """Delete selected"""
        self.timeline.delete_selected()
        self.is_modified = True
        
    def _add_track(self):
        """Add a new track"""
        track_id = self.track_panel.add_track()
        self.timeline.add_track(track_id)
        self.is_modified = True
        
    def _remove_track(self):
        """Remove selected track"""
        track_id = self.track_panel.get_selected_track()
        if track_id:
            self.track_panel.remove_track(track_id)
            self.timeline.remove_track(track_id)
            self.is_modified = True
            
    def _zoom_in(self):
        """Zoom in on timeline"""
        self.timeline.zoom_in()
        
    def _zoom_out(self):
        """Zoom out on timeline"""
        self.timeline.zoom_out()
        
    def _zoom_fit(self):
        """Zoom to fit all content"""
        self.timeline.zoom_to_fit()
        
    def _toggle_chat(self):
        """Toggle AI chat visibility"""
        if self.chat_dock.isVisible():
            self.chat_dock.hide()
        else:
            self.chat_dock.show()
            
    def _generate_music(self):
        """Open music generation dialog"""
        self.chat_widget.show()
        self.chat_dock.show()
        self.chat_widget.focus_input()
        
    def _show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self, "About AI-Integrated DAW",
            "<h2>AI-Integrated DAW</h2>"
            "<p>Version 1.0</p>"
            "<p>A Digital Audio Workstation with AI-powered music generation.</p>"
            "<p>Features multi-track editing, waveform visualization, "
            "and ElevenLabs AI integration.</p>"
        )
        
    # ===== Transport Control Handlers =====
    
    def _on_play(self):
        """Handle play button"""
        self.status_label.setText("Playing...")
        self.audio_engine.clear()
        for clip in self.timeline.clips.values():
            if isinstance(clip, MidiClip):
                continue
            self.audio_engine.load_audio(clip)
        rendered_midi = set()
        for clip in list(self.timeline.clips.values()) + list(self.midi_clips):
            if not isinstance(clip, MidiClip):
                continue
            cid = getattr(clip, "id", id(clip))
            if cid in rendered_midi:
                continue
            rendered_midi.add(cid)
            if not clip.notes:
                continue
            audio = midi_synth.render_midi(
                clip.notes, instrument=clip.instrument, bpm=clip.bpm
            )
            start = getattr(clip, "start_time", 0.0) or 0.0
            self.audio_engine.load_audio(clip.track_id, audio, start=start)
        self.audio_engine.play(start_position=self.timeline.playhead_position)
        self.timeline.start_playback()
        
    def _on_pause(self):
        """Handle pause button"""
        self.status_label.setText("Paused")
        self.audio_engine.pause()
        self.timeline.pause_playback()
        
    def _on_stop(self):
        """Handle stop button"""
        self.status_label.setText("Stopped")
        self.audio_engine.stop()
        self.timeline.stop_playback()

    def _on_playback_position(self, position):
        """Keep the status-bar clock on the engine playhead"""
        minutes = int(position // 60)
        seconds = int(position % 60)
        millis = int((position % 1) * 1000)
        self.position_label.setText(f"{minutes:02d}:{seconds:02d}:{millis:03d}")

    def _on_engine_finished(self):
        """Engine reached the end of the mix"""
        self.status_label.setText("Stopped")
        self.timeline.stop_playback()

    def _on_engine_error(self, message):
        """Surface engine errors in the status bar"""
        self.status_label.setText(message)
        
    def _on_record(self):
        """Handle record button"""
        self.status_label.setText("Recording...")
        
    def _on_bpm_changed(self, bpm):
        """Handle BPM change"""
        self.timeline.set_bpm(bpm)
        
    def _clip_for_selected_track(self) -> MidiClip:
        """Return the MidiClip the piano roll should edit for the selected track."""
        track_id = self.track_panel.get_selected_track()
        if track_id is None:
            track_id = 0
        for clip in self.midi_clips:
            if clip.track_id == track_id:
                return clip
        bpm = float(getattr(self.transport, "bpm", 120) or 120)
        clip = MidiClip(track_id=track_id, name=f"MIDI {track_id}", bpm=bpm)
        self.midi_clips.append(clip)
        return clip

    def _on_track_output_changed(self, track_id, dest):
        """Write picker dest through engine.set_track_output; revert on reject."""
        engine = getattr(self, "audio_engine", None)
        if engine is None:
            return
        try:
            engine.set_track_output(track_id, dest)
        except ValueError:
            self.track_panel.set_track_output(
                track_id, engine.get_track_output(track_id)
            )
            return
        self.is_modified = True

    def _on_track_selected(self, track_id: int):
        """Point the piano roll at this track's MidiClip."""
        clip = None
        for existing in self.midi_clips:
            if existing.track_id == track_id:
                clip = existing
                break
        if clip is None:
            bpm = float(getattr(self.transport, "bpm", 120) or 120)
            clip = MidiClip(track_id=track_id, name=f"MIDI {track_id}", bpm=bpm)
            self.midi_clips.append(clip)
        self.piano_roll.set_clip(clip)

    def _on_midi_note_added(self, note):
        self.is_modified = True

    def _on_stage_approved(self, stage: str):
        """Apply tracks when the track stage is approved (chat may emit the next stage)."""
        if stage in ("track", "mixing", "complete"):
            self._apply_session_track_data()

    def _on_agent_production_complete(self, session_id: str, final_data: dict):
        self._apply_session_track_data(final_data=final_data, session_id=session_id)

    def apply_track_data(self, track_data=None, session_id=None):
        """Apply TrackData / dict, or write the fallback pop sketch."""
        if track_data is None:
            return self._apply_session_track_data(session_id=session_id)
        if isinstance(track_data, dict) and "track_data" in track_data:
            return self._apply_session_track_data(final_data=track_data, session_id=session_id)
        return self._apply_session_track_data(
            final_data={"track_data": track_data}, session_id=session_id
        )

    def _apply_session_track_data(self, final_data=None, session_id=None):
        """Create timeline tracks and MidiClips from session.track_data."""
        sid = session_id or getattr(self.chat_widget, "session_id", None)
        if sid and sid == self._applied_track_session:
            return

        session = None
        if sid and hasattr(self, "agent_manager"):
            session = self.agent_manager.get_session(sid)

        track_data = None
        inst_tracks = []
        bpm = float(getattr(self.transport, "bpm", 120) or 120)

        if session is not None:
            track_data = session.track_data
            if session.production_plan and getattr(session.production_plan, "tempo_bpm", None):
                bpm = float(session.production_plan.tempo_bpm or bpm)
            plan = session.instrumentation_plan
            if plan is not None and getattr(plan, "tracks", None):
                inst_tracks = list(plan.tracks)

        if final_data is not None:
            if hasattr(final_data, "midi_patterns") and not isinstance(final_data, dict):
                track_data = final_data
            elif isinstance(final_data, dict):
                td = final_data.get("track_data")
                if td:
                    track_data = td
                pp = final_data.get("production_plan") or {}
                if isinstance(pp, dict) and pp.get("tempo_bpm"):
                    bpm = float(pp["tempo_bpm"])
                ip = final_data.get("instrumentation_plan") or {}
                if isinstance(ip, dict) and ip.get("tracks"):
                    inst_tracks = list(ip["tracks"])

        patterns = []
        created = []
        if track_data is not None:
            if hasattr(track_data, "midi_patterns"):
                patterns = list(track_data.midi_patterns or [])
                created = list(getattr(track_data, "created_tracks", None) or [])
            elif isinstance(track_data, dict):
                patterns = list(track_data.get("midi_patterns") or [])
                created = list(track_data.get("created_tracks") or [])

        if not patterns:
            self._apply_fallback_pop_sketch(bpm)
        else:
            self._apply_midi_patterns(patterns, created, inst_tracks, bpm)

        if sid:
            self._applied_track_session = sid
        self.piano_roll.set_clip(self._clip_for_selected_track())
        self.is_modified = True

    def _instrument_kind(self, name: str) -> str:
        blob = (name or "").lower()
        if any(w in blob for w in ("drum", "kick", "snare", "hat", "perc", "kit")):
            return "drums"
        if "bass" in blob:
            return "bass"
        if any(w in blob for w in ("lead", "synth", "saw")):
            return "lead"
        return "piano"

    def _ensure_named_track(self, name: str) -> int:
        name = name or "Track"
        for tid, widget in self.track_panel.tracks.items():
            if getattr(widget, "name", None) == name:
                if tid not in self.timeline.tracks:
                    self.timeline.add_track(tid, name)
                return tid
        tid = self.track_panel.add_track(name)
        self.timeline.add_track(tid, name)
        return tid

    def _notes_from_pattern(self, raw_notes):
        notes = []
        for n in raw_notes or []:
            if isinstance(n, MidiNote):
                notes.append(n)
                continue
            if not isinstance(n, dict):
                continue
            data = {
                "pitch": n.get("pitch", n.get("note", 60)),
                "start_beat": n.get("start_beat", n.get("beat", 0.0)),
                "duration_beats": n.get("duration_beats", n.get("duration", 1.0)),
                "velocity": n.get("velocity", 100),
            }
            notes.append(MidiNote.from_dict(data))
        return notes

    def _apply_midi_patterns(self, patterns, created, inst_tracks, bpm):
        for spec in list(created) + list(inst_tracks):
            if not isinstance(spec, dict):
                continue
            name = (
                spec.get("instrument")
                or spec.get("track_name")
                or spec.get("name")
                or spec.get("track")
            )
            if name:
                self._ensure_named_track(str(name))

        last_clip = None
        for pattern in patterns:
            if not isinstance(pattern, dict):
                continue
            track_name = (
                pattern.get("track")
                or pattern.get("instrument")
                or pattern.get("name")
                or "MIDI"
            )
            tid = self._ensure_named_track(str(track_name))
            notes = self._notes_from_pattern(pattern.get("notes"))
            if not notes:
                continue
            clip = MidiClip(
                name=str(track_name),
                track_id=tid,
                instrument=self._instrument_kind(str(track_name)),
                bpm=float(bpm),
                notes=notes,
            )
            start_bar = float(pattern.get("start_bar", 0) or 0)
            start_time = start_bar * 4.0 * (60.0 / float(bpm or 120))
            clip.start_time = start_time
            self.midi_clips.append(clip)
            if tid in self.timeline.tracks:
                self.timeline.add_clip(tid, clip, start_time)
            last_clip = clip

        if last_clip is not None:
            self.piano_roll.set_clip(last_clip)
        self.status_label.setText("Applied session MIDI to the timeline")

    def _apply_fallback_pop_sketch(self, bpm=120.0):
        """Drums + bass + piano sketch so Play is audible without an LLM."""
        bpm = float(bpm or 120)
        specs = [
            (
                "Drums",
                "drums",
                [
                    (36, 0.0, 0.5, 110), (36, 2.0, 0.5, 110),
                    (36, 4.0, 0.5, 110), (36, 6.0, 0.5, 110),
                    (38, 1.0, 0.4, 108), (38, 3.0, 0.4, 108),
                    (38, 5.0, 0.4, 108), (38, 7.0, 0.4, 108),
                    (42, 0.5, 0.25, 80), (42, 1.5, 0.25, 80),
                    (42, 2.5, 0.25, 80), (42, 3.5, 0.25, 80),
                    (42, 4.5, 0.25, 80), (42, 5.5, 0.25, 80),
                    (42, 6.5, 0.25, 80), (42, 7.5, 0.25, 80),
                ],
            ),
            (
                "Bass",
                "bass",
                [
                    (36, 0.0, 1.0, 100), (36, 1.0, 0.5, 90),
                    (38, 2.0, 1.0, 100), (41, 4.0, 1.0, 100),
                    (38, 6.0, 1.0, 100), (36, 7.0, 0.75, 95),
                ],
            ),
            (
                "Piano",
                "piano",
                [
                    (60, 0.0, 2.0, 90), (64, 0.0, 2.0, 85), (67, 0.0, 2.0, 85),
                    (65, 2.0, 2.0, 90), (69, 2.0, 2.0, 85), (72, 2.0, 2.0, 85),
                    (60, 4.0, 2.0, 90), (64, 4.0, 2.0, 85), (67, 4.0, 2.0, 85),
                    (62, 6.0, 2.0, 88), (65, 6.0, 2.0, 82), (69, 6.0, 2.0, 82),
                ],
            ),
        ]
        last_clip = None
        for name, inst, notes in specs:
            tid = self._ensure_named_track(name)
            clip = MidiClip(name=name, track_id=tid, instrument=inst, bpm=bpm)
            for pitch, start, dur, vel in notes:
                clip.add_note(pitch, start, dur, vel)
            clip.start_time = 0.0
            self.midi_clips.append(clip)
            if tid in self.timeline.tracks:
                self.timeline.add_clip(tid, clip, 0.0)
            last_clip = clip
        if last_clip is not None:
            self.piano_roll.set_clip(last_clip)
        self.status_label.setText("Applied fallback pop sketch (drums, bass, piano)")

    # ===== Helper Methods =====
    
    def _check_save(self):
        """Check if project needs saving before closing"""
        if self.is_modified:
            reply = QMessageBox.question(
                self, "Save Changes?",
                "The project has been modified. Save changes?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Save:
                self._save_project()
                return True
            elif reply == QMessageBox.StandardButton.Cancel:
                return False
        return True
        
    def _update_title(self):
        """Update window title with project name"""
        title = "AI-Integrated DAW"
        if self.current_project_path:
            name = os.path.basename(self.current_project_path)
            title = f"{title} - {name}"
        if self.is_modified:
            title = f"{title} *"
        self.setWindowTitle(title)
        
    def _get_project_data(self):
        """Get current project data for saving (schema 1.1 envelope).

        Graph keys (buses / outputs / sends) are overlaid from the engine
        in ProjectManager.save_project. Inserts and clip maps are carried
        from the last loaded/new project so File>Save does not drop them.
        """
        prior = getattr(self.project_manager, "current_project", None) or {}
        data = {
            'version': ProjectManager.SCHEMA_VERSION,
            'timeline': self.timeline.get_state(),
            'tracks': self.track_panel.get_state(),
            'transport': self.transport.get_state(),
            'clips': prior.get('clips') if prior.get('clips') is not None else {},
            'midi_clips': prior.get('midi_clips') if prior.get('midi_clips') is not None else {},
            'inserts': prior.get('inserts') if prior.get('inserts') is not None else {},
        }
        if prior.get('name') is not None:
            data['name'] = prior['name']
        if prior.get('created_at') is not None:
            data['created_at'] = prior['created_at']
        if prior.get('settings') is not None:
            data['settings'] = prior['settings']
        return data
        
    def _load_project_data(self, data):
        """Load project data into UI"""
        if 'timeline' in data:
            self.timeline.set_state(data['timeline'])
        if 'tracks' in data:
            self.track_panel.set_state(data['tracks'])
        if 'transport' in data:
            self.transport.set_state(data['transport'])
        outputs = data.get('track_outputs')
        self.audio_engine.clear()
        for clip in self.timeline.clips.values():
            self.audio_engine.load_audio(clip)
        # clear() wipes in-session buses/sends; restore after clips so
        # unused buses and send-to-track dests can be live.
        self.project_manager._apply_buses(self.audio_engine, data.get('buses'))
        self.project_manager._apply_bus_mixer(self.audio_engine, data)
        self.project_manager._apply_track_outputs(self.audio_engine, outputs)
        self.project_manager._apply_inserts(self.audio_engine, data.get('inserts'))
        self.project_manager._apply_sends(
            self.audio_engine,
            data.get('track_sends'),
            data.get('track_send_levels'),
            data.get('track_send_modes'),
        )
        self.track_panel.sync_outputs_from_engine(self.audio_engine)
            
    def _autosave(self):
        """Auto-save project"""
        if self.is_modified and self.current_project_path:
            # Save to autosave location
            autosave_path = os.path.join(
                os.path.dirname(self.current_project_path),
                ".autosave",
                os.path.basename(self.current_project_path)
            )
            try:
                project_data = self._get_project_data()
                self.project_manager.save_project(
                    autosave_path, project_data, engine=self.audio_engine
                )
                self.status_label.setText("Auto-saved")
            except:
                pass
                
    def closeEvent(self, event):
        """Handle window close"""
        # Hidden/offscreen closes (pytest) must not block on the save dialog.
        if self.isVisible() and not self._check_save():
            event.ignore()
            return
        self.audio_engine.stop()
        manager = getattr(self, "agent_manager", None)
        if manager is not None and hasattr(manager, "close"):
            try:
                manager.close()
            except Exception:
                pass
        event.accept()


def main():
    """Application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("AI-Integrated DAW")
    app.setApplicationVersion("1.0")
    
    # Set application style
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
