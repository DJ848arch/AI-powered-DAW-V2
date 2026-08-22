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
        
    # ===== Action Handlers =====
    
    def _new_project(self):
        """Create a new project"""
        if self._check_save():
            self.project_manager.new_project()
            self.timeline.clear()
            self.track_panel.clear()
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
                project_data = self.project_manager.load_project(file_path)
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
            self.project_manager.save_project(file_path, project_data)
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
        """Get current project data for saving"""
        return {
            'timeline': self.timeline.get_state(),
            'tracks': self.track_panel.get_state(),
            'transport': self.transport.get_state()
        }
        
    def _load_project_data(self, data):
        """Load project data into UI"""
        if 'timeline' in data:
            self.timeline.set_state(data['timeline'])
        if 'tracks' in data:
            self.track_panel.set_state(data['tracks'])
        if 'transport' in data:
            self.transport.set_state(data['transport'])
            
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
                self.project_manager.save_project(autosave_path, project_data)
                self.status_label.setText("Auto-saved")
            except:
                pass
                
    def closeEvent(self, event):
        """Handle window close"""
        if self._check_save():
            self.audio_engine.stop()
            event.accept()
        else:
            event.ignore()


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
