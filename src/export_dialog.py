"""
Audio Export Dialog
Handles audio export to WAV/MP3/FLAC
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QComboBox, QSpinBox,
    QGroupBox, QCheckBox, QProgressBar, QFileDialog,
    QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont
import os


class ExportDialog(QDialog):
    """Dialog for exporting audio"""
    
    def __init__(self, parent=None, project_duration: float = 60.0):
        super().__init__(parent)
        
        self.project_duration = project_duration
        self.export_path = None
        
        self.setWindowTitle("Export Audio")
        self.setMinimumWidth(400)
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Set up the UI"""
        self.setStyleSheet("""
            QDialog {
                background: #2a2a2a;
            }
            QLabel {
                color: #ccc;
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
            QLineEdit {
                background: #444;
                border: 1px solid #555;
                color: white;
                padding: 6px;
            }
            QComboBox, QSpinBox {
                background: #444;
                border: 1px solid #555;
                color: white;
                padding: 4px;
            }
            QPushButton {
                background: #4a9eff;
                border: none;
                padding: 8px 16px;
                color: white;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #5aafff;
            }
            QPushButton:disabled {
                background: #444;
                color: #888;
            }
            QCheckBox {
                color: #ccc;
            }
            QProgressBar {
                border: 1px solid #444;
                background: #1a1a1a;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background: #4a9eff;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # File selection
        file_group = QGroupBox("Export Location")
        file_layout = QVBoxLayout(file_group)
        
        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Select export location...")
        path_layout.addWidget(self.path_edit)
        
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse_file)
        path_layout.addWidget(self.browse_btn)
        
        file_layout.addLayout(path_layout)
        layout.addWidget(file_group)
        
        # Format settings
        format_group = QGroupBox("Format Settings")
        format_layout = QVBoxLayout(format_group)
        
        # Format
        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["WAV", "MP3", "FLAC", "OGG"])
        self.format_combo.currentTextChanged.connect(self._on_format_changed)
        format_row.addWidget(self.format_combo)
        format_layout.addLayout(format_row)
        
        # Sample rate
        sr_row = QHBoxLayout()
        sr_row.addWidget(QLabel("Sample Rate:"))
        self.sr_combo = QComboBox()
        self.sr_combo.addItems(["44100 Hz", "48000 Hz", "88200 Hz", "96000 Hz"])
        self.sr_combo.setCurrentIndex(0)
        sr_row.addWidget(self.sr_combo)
        format_layout.addLayout(sr_row)
        
        # Bit depth / Quality
        quality_row = QHBoxLayout()
        quality_row.addWidget(QLabel("Quality:"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems([
            "16-bit / 128 kbps",
            "24-bit / 192 kbps",
            "32-bit / 320 kbps"
        ])
        quality_row.addWidget(self.quality_combo)
        format_layout.addLayout(quality_row)
        
        layout.addWidget(format_group)
        
        # Export range
        range_group = QGroupBox("Export Range")
        range_layout = QVBoxLayout(range_group)
        
        # Full project
        self.full_project_check = QCheckBox("Export full project")
        self.full_project_check.setChecked(True)
        self.full_project_check.toggled.connect(self._on_range_changed)
        range_layout.addWidget(self.full_project_check)
        
        # Custom range
        custom_layout = QHBoxLayout()
        custom_layout.addWidget(QLabel("Start:"))
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, int(self.project_duration))
        self.start_spin.setSuffix(" s")
        self.start_spin.setEnabled(False)
        custom_layout.addWidget(self.start_spin)
        
        custom_layout.addWidget(QLabel("End:"))
        self.end_spin = QSpinBox()
        self.end_spin.setRange(0, int(self.project_duration * 2))
        self.end_spin.setValue(int(self.project_duration))
        self.end_spin.setSuffix(" s")
        self.end_spin.setEnabled(False)
        custom_layout.addWidget(self.end_spin)
        
        range_layout.addLayout(custom_layout)
        layout.addWidget(range_group)
        
        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)
        
        self.normalize_check = QCheckBox("Normalize audio")
        self.normalize_check.setChecked(True)
        options_layout.addWidget(self.normalize_check)
        
        self.dither_check = QCheckBox("Apply dithering")
        self.dither_check.setChecked(True)
        options_layout.addWidget(self.dither_check)
        
        layout.addWidget(options_group)
        
        # Progress bar (hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self._on_export)
        button_layout.addWidget(self.export_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: #444;
            }
        """)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        
    def _browse_file(self):
        """Browse for export file"""
        format_filter = {
            "WAV": "WAV Files (*.wav)",
            "MP3": "MP3 Files (*.mp3)",
            "FLAC": "FLAC Files (*.flac)",
            "OGG": "OGG Files (*.ogg)"
        }
        
        current_format = self.format_combo.currentText()
        file_filter = format_filter.get(current_format, "All Files (*)")
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Audio", "", file_filter
        )
        
        if file_path:
            # Ensure correct extension
            ext = current_format.lower()
            if not file_path.lower().endswith(f".{ext}"):
                file_path += f".{ext}"
            self.path_edit.setText(file_path)
            
    def _on_format_changed(self, format_name):
        """Handle format change"""
        # Update quality options based on format
        self.quality_combo.clear()
        
        if format_name == "WAV" or format_name == "FLAC":
            self.quality_combo.addItems([
                "16-bit PCM",
                "24-bit PCM",
                "32-bit Float"
            ])
        else:
            self.quality_combo.addItems([
                "128 kbps",
                "192 kbps",
                "256 kbps",
                "320 kbps"
            ])
            
    def _on_range_changed(self, full_project):
        """Handle range selection change"""
        self.start_spin.setEnabled(not full_project)
        self.end_spin.setEnabled(not full_project)
        
    def _on_export(self):
        """Handle export button"""
        file_path = self.path_edit.text()
        
        if not file_path:
            QMessageBox.warning(self, "Export Error", "Please select an export location.")
            return
            
        self.export_path = file_path
        self.accept()
        
    def get_export_settings(self):
        """Get export settings"""
        return {
            'path': self.export_path,
            'format': self.format_combo.currentText().lower(),
            'sample_rate': int(self.sr_combo.currentText().split()[0]),
            'quality': self.quality_combo.currentText(),
            'full_project': self.full_project_check.isChecked(),
            'start_time': self.start_spin.value() if not self.full_project_check.isChecked() else 0,
            'end_time': self.end_spin.value() if not self.full_project_check.isChecked() else None,
            'normalize': self.normalize_check.isChecked(),
            'dither': self.dither_check.isChecked()
        }


class ExportWorker(QThread):
    """Worker thread for audio export"""
    
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, audio_engine, settings):
        super().__init__()
        self.audio_engine = audio_engine
        self.settings = settings
        
    def run(self):
        """Run export"""
        try:
            from audio_engine import AudioExporter
            
            exporter = AudioExporter(self.audio_engine)
            exporter.export_progress.connect(self.progress.emit)
            
            exporter.export(
                output_path=self.settings['path'],
                format=self.settings['format'],
                start_time=self.settings['start_time'],
                end_time=self.settings['end_time']
            )
            
            self.finished.emit(self.settings['path'])
            
        except Exception as e:
            self.error.emit(str(e))
