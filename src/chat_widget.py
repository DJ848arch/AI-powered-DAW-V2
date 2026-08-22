"""
AI Agent Chat Interface for Multi-Agent Music Production
Supports 5 specialized agents: Brainstorming → Producer → Conductor → Track → Mixing
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QLineEdit, QPushButton, QLabel, QScrollArea,
    QFrame, QSplitter, QComboBox, QProgressBar,
    QMessageBox, QFileDialog, QGroupBox, QTreeWidget,
    QTreeWidgetItem, QTabWidget, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt6.QtGui import QTextCursor, QColor, QTextCharFormat, QFont
import time
import json


class ChatWidget(QWidget):
    """AI chat interface for multi-agent music production"""
    
    # Signals
    message_sent = pyqtSignal(str)
    music_generated = pyqtSignal(str)  # Path to generated audio
    stage_approved = pyqtSignal(str)  # stage name
    revision_requested = pyqtSignal(str, str)  # stage, feedback
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.agent_manager = None  # Will be set externally
        self.session_id = None
        self.chat_history = []
        self.is_generating = False
        self.current_stage = "brainstorming"
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Set up the UI"""
        self.setStyleSheet("""
            ChatWidget {
                background: #2a2a2a;
            }
            QTextEdit {
                background: #1a1a1a;
                border: 1px solid #444;
                color: #eee;
                font-family: 'Consolas', monospace;
                font-size: 12px;
            }
            QLineEdit {
                background: #333;
                border: 1px solid #555;
                color: white;
                padding: 8px;
                font-size: 12px;
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
            QPushButton#approveBtn {
                background: #4caf50;
            }
            QPushButton#approveBtn:hover {
                background: #5cbf60;
            }
            QPushButton#reviseBtn {
                background: #ff9800;
            }
            QPushButton#reviseBtn:hover {
                background: #ffa726;
            }
            QLabel {
                color: #ccc;
            }
            QLabel#stageLabel {
                color: #4a9eff;
                font-weight: bold;
                font-size: 13px;
            }
            QLabel#agentLabel {
                color: #90ee90;
                font-weight: bold;
                font-size: 12px;
            }
            QComboBox {
                background: #333;
                border: 1px solid #555;
                color: white;
                padding: 4px;
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
            QGroupBox {
                border: 1px solid #555;
                margin-top: 10px;
                padding-top: 10px;
                color: #ccc;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QTreeWidget {
                background: #1a1a1a;
                border: 1px solid #444;
                color: #eee;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:selected {
                background: #4a9eff;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Header with pipeline stages
        header_layout = QHBoxLayout()
        
        header = QLabel("AI Music Production Pipeline")
        header.setStyleSheet("font-size: 14px; font-weight: bold; color: #4a9eff;")
        header_layout.addWidget(header)
        header_layout.addStretch()
        
        # New Session button
        self.new_session_btn = QPushButton("New Session")
        self.new_session_btn.setStyleSheet("""
            QPushButton {
                background: #6a4cff;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #7a5cff;
            }
        """)
        self.new_session_btn.clicked.connect(self._start_new_session)
        header_layout.addWidget(self.new_session_btn)
        
        layout.addLayout(header_layout)
        
        # Pipeline Stage Indicator
        self._setup_pipeline_indicator(layout)
        
        # Current Agent Display
        agent_display_layout = QHBoxLayout()
        agent_display_layout.addWidget(QLabel("Current Agent:"))
        
        self.current_agent_label = QLabel("Brainstorming Agent")
        self.current_agent_label.setObjectName("agentLabel")
        agent_display_layout.addWidget(self.current_agent_label)
        agent_display_layout.addStretch()
        
        self.current_stage_label = QLabel("Stage: Brainstorming")
        self.current_stage_label.setObjectName("stageLabel")
        agent_display_layout.addWidget(self.current_stage_label)
        
        layout.addLayout(agent_display_layout)
        
        # Main content area with splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side: Chat
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        
        # Chat display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setMinimumHeight(300)
        chat_layout.addWidget(self.chat_display)
        
        # Approval buttons (hidden by default)
        self.approval_widget = QWidget()
        approval_layout = QHBoxLayout(self.approval_widget)
        approval_layout.setContentsMargins(0, 5, 0, 5)
        
        approval_label = QLabel("Approve this stage?")
        approval_label.setStyleSheet("color: #ffd93d; font-weight: bold;")
        approval_layout.addWidget(approval_label)
        approval_layout.addStretch()
        
        self.approve_btn = QPushButton("✓ Approve & Continue")
        self.approve_btn.setObjectName("approveBtn")
        self.approve_btn.clicked.connect(self._on_approve_stage)
        approval_layout.addWidget(self.approve_btn)
        
        self.revise_btn = QPushButton("✎ Request Changes")
        self.revise_btn.setObjectName("reviseBtn")
        self.revise_btn.clicked.connect(self._on_request_revision)
        approval_layout.addWidget(self.revise_btn)
        
        self.approval_widget.hide()
        chat_layout.addWidget(self.approval_widget)
        
        # Input area
        input_layout = QHBoxLayout()
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Describe what you'd like to create...")
        self.input_field.returnPressed.connect(self._send_message)
        input_layout.addWidget(self.input_field)
        
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self.send_btn)
        
        chat_layout.addLayout(input_layout)
        
        splitter.addWidget(chat_widget)
        
        # Right side: Structured Data Panel
        self.data_panel = self._create_data_panel()
        self.data_panel.setMinimumWidth(250)
        self.data_panel.setMaximumWidth(350)
        splitter.addWidget(self.data_panel)
        
        splitter.setSizes([600, 300])
        layout.addWidget(splitter)
        
        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        
        # Action buttons
        action_layout = QHBoxLayout()
        
        self.generate_btn = QPushButton("🎵 Generate Music")
        self.generate_btn.setToolTip("Generate music based on conversation")
        self.generate_btn.clicked.connect(self._generate_music)
        action_layout.addWidget(self.generate_btn)
        
        self.import_btn = QPushButton("📥 Import Audio")
        self.import_btn.setToolTip("Import generated audio to timeline")
        self.import_btn.clicked.connect(self._import_audio)
        self.import_btn.setEnabled(False)
        action_layout.addWidget(self.import_btn)
        
        self.clear_btn = QPushButton("Clear Chat")
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background: #444;
            }
        """)
        self.clear_btn.clicked.connect(self._clear_chat)
        action_layout.addWidget(self.clear_btn)
        
        action_layout.addStretch()
        layout.addLayout(action_layout)
        
        # Status label
        self.status_label = QLabel("Ready - Start a new session to begin")
        self.status_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self.status_label)
        
    def _setup_pipeline_indicator(self, parent_layout):
        """Setup the pipeline stage indicator"""
        pipeline_group = QGroupBox("Production Pipeline")
        pipeline_layout = QHBoxLayout(pipeline_group)
        pipeline_layout.setSpacing(5)
        
        self.stage_labels = {}
        stages = [
            ("brainstorming", "🎨", "Brainstorm"),
            ("producer", "🎬", "Producer"),
            ("conductor", "🎼", "Conductor"),
            ("track", "🎹", "Track"),
            ("mixing", "🎛️", "Mixing"),
        ]
        
        for i, (stage_id, icon, name) in enumerate(stages):
            # Stage indicator
            stage_widget = QWidget()
            stage_layout = QVBoxLayout(stage_widget)
            stage_layout.setContentsMargins(5, 2, 5, 2)
            stage_layout.setSpacing(2)
            
            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size: 16px;")
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stage_layout.addWidget(icon_label)
            
            name_label = QLabel(name)
            name_label.setStyleSheet("font-size: 9px; color: #888;")
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stage_layout.addWidget(name_label)
            
            # Status indicator
            status_label = QLabel("○")
            status_label.setStyleSheet("font-size: 12px; color: #555;")
            status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stage_layout.addWidget(status_label)
            
            self.stage_labels[stage_id] = {
                "widget": stage_widget,
                "icon": icon_label,
                "name": name_label,
                "status": status_label
            }
            
            pipeline_layout.addWidget(stage_widget)
            
            # Add arrow between stages (except last)
            if i < len(stages) - 1:
                arrow = QLabel("→")
                arrow.setStyleSheet("color: #555; font-size: 14px;")
                pipeline_layout.addWidget(arrow)
        
        pipeline_layout.addStretch()
        parent_layout.addWidget(pipeline_group)
        
    def _create_data_panel(self) -> QWidget:
        """Create the structured data display panel"""
        panel = QTabWidget()
        panel.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #444;
                background: #1a1a1a;
            }
            QTabBar::tab {
                background: #333;
                color: #888;
                padding: 6px 12px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #4a9eff;
                color: white;
            }
        """)
        
        # Tab 1: Current Data
        self.data_tree = QTreeWidget()
        self.data_tree.setHeaderLabel("Production Data")
        self.data_tree.setColumnCount(1)
        panel.addTab(self.data_tree, "📊 Data")
        
        # Tab 2: Session Info
        self.session_info = QTextEdit()
        self.session_info.setReadOnly(True)
        self.session_info.setPlainText("No active session\n\nStart a new session to begin the production pipeline.")
        panel.addTab(self.session_info, "ℹ️ Info")
        
        # Tab 3: Quick Prompts
        prompts_widget = QWidget()
        prompts_layout = QVBoxLayout(prompts_widget)
        prompts_layout.setContentsMargins(10, 10, 10, 10)
        
        prompts_label = QLabel("Quick Prompts:")
        prompts_label.setStyleSheet("font-weight: bold; color: #4a9eff;")
        prompts_layout.addWidget(prompts_label)
        
        prompts = [
            ("🎵 Genre", ["Make a pop beat", "Create hip hop drums", "House music vibe", "Trap beat"]),
            ("🎹 Elements", ["Add a bassline", "Create melody", "Chord progression", "Add pads"]),
            ("🎛️ Production", ["Four-on-the-floor", "Sidechain compression", "Build a drop", "Add reverb"]),
        ]
        
        for category, items in prompts:
            cat_label = QLabel(category)
            cat_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
            prompts_layout.addWidget(cat_label)
            
            for item in items:
                btn = QPushButton(item)
                btn.setStyleSheet("""
                    QPushButton {
                        background: #3a3a3a;
                        border: 1px solid #555;
                        padding: 4px 8px;
                        font-size: 10px;
                        text-align: left;
                    }
                    QPushButton:hover {
                        background: #4a4a4a;
                    }
                """)
                btn.clicked.connect(lambda checked, s=item: self._on_suggestion(s))
                prompts_layout.addWidget(btn)
        
        prompts_layout.addStretch()
        panel.addTab(prompts_widget, "⚡ Prompts")
        
        return panel
        
    def set_agent_manager(self, agent_manager):
        """Set the agent manager"""
        self.agent_manager = agent_manager
        
        # Connect to agent manager signals
        if agent_manager:
            agent_manager.stage_changed.connect(self._on_stage_changed)
            agent_manager.response_received.connect(self._on_agent_response)
            agent_manager.production_complete.connect(self._on_production_complete)
            
    def _start_new_session(self):
        """Start a new production session"""
        if not self.agent_manager:
            self._add_system_message("Error: Agent manager not configured")
            return
            
        self.session_id = self.agent_manager.start_production_session()
        self.current_stage = "brainstorming"
        
        # Clear chat and update UI
        self.chat_display.clear()
        self.chat_history.clear()
        
        # Update stage indicator
        self._update_stage_indicator("brainstorming")
        
        # Update data panel
        self._update_data_panel()
        
        # Add welcome message
        greeting = self.agent_manager._generate_agent_greeting("brainstorming")
        self._add_agent_message("Brainstorming Agent", greeting)
        
        self.status_label.setText(f"Session started: {self.session_id[:8]}...")
        self.session_info.setPlainText(f"Session ID: {self.session_id}\nStage: Brainstorming\n\nReady to discuss your musical vision!")
        
    def _update_stage_indicator(self, current_stage: str):
        """Update the pipeline stage indicator"""
        stages = ["brainstorming", "producer", "conductor", "track", "mixing"]
        current_idx = stages.index(current_stage) if current_stage in stages else -1
        
        for i, stage_id in enumerate(stages):
            labels = self.stage_labels[stage_id]
            
            if i < current_idx:
                # Completed stage
                labels["status"].setText("✓")
                labels["status"].setStyleSheet("font-size: 12px; color: #4caf50;")
                labels["name"].setStyleSheet("font-size: 9px; color: #4caf50;")
            elif i == current_idx:
                # Current stage
                labels["status"].setText("●")
                labels["status"].setStyleSheet("font-size: 12px; color: #4a9eff;")
                labels["name"].setStyleSheet("font-size: 9px; color: #4a9eff; font-weight: bold;")
            else:
                # Future stage
                labels["status"].setText("○")
                labels["status"].setStyleSheet("font-size: 12px; color: #555;")
                labels["name"].setStyleSheet("font-size: 9px; color: #888;")
                
    def _update_data_panel(self):
        """Update the structured data panel"""
        if not self.session_id or not self.agent_manager:
            return
            
        session = self.agent_manager.get_session(self.session_id)
        if not session:
            return
            
        self.data_tree.clear()
        
        # Add brainstorm data
        if session.brainstorm_data:
            bd = session.brainstorm_data
            brainstorm_item = QTreeWidgetItem(self.data_tree, ["🎨 Brainstorm Data"])
            if bd.genre:
                QTreeWidgetItem(brainstorm_item, [f"Genre: {bd.genre}"])
            if bd.mood:
                QTreeWidgetItem(brainstorm_item, [f"Mood: {bd.mood}"])
            if bd.tempo_preference:
                QTreeWidgetItem(brainstorm_item, [f"Tempo: {bd.tempo_preference}"])
            if bd.key_preference:
                QTreeWidgetItem(brainstorm_item, [f"Key: {bd.key_preference}"])
            brainstorm_item.setExpanded(True)
            
        # Add production plan
        if session.production_plan:
            pp = session.production_plan
            plan_item = QTreeWidgetItem(self.data_tree, ["🎬 Production Plan"])
            QTreeWidgetItem(plan_item, [f"Tempo: {pp.tempo_bpm} BPM"])
            QTreeWidgetItem(plan_item, [f"Key: {pp.key}"])
            QTreeWidgetItem(plan_item, [f"Duration: {pp.duration_bars} bars"])
            if pp.sections:
                sections_item = QTreeWidgetItem(plan_item, ["Sections"])
                for section in pp.sections:
                    QTreeWidgetItem(sections_item, [f"{section['name']}: {section['bars']} bars ({section['energy']})"])
            plan_item.setExpanded(True)
            
        # Add instrumentation
        if session.instrumentation_plan:
            ip = session.instrumentation_plan
            inst_item = QTreeWidgetItem(self.data_tree, ["🎼 Instrumentation"])
            if ip.tracks:
                tracks_item = QTreeWidgetItem(inst_item, [f"Tracks ({len(ip.tracks)})"])
                for track in ip.tracks:
                    QTreeWidgetItem(tracks_item, [f"{track['name']}: {track['instrument']}"])
            inst_item.setExpanded(True)
            
        # Add track data
        if session.track_data:
            td = session.track_data
            track_item = QTreeWidgetItem(self.data_tree, ["🎹 Track Data"])
            QTreeWidgetItem(track_item, [f"Tracks: {len(td.created_tracks)}"])
            QTreeWidgetItem(track_item, [f"MIDI Patterns: {len(td.midi_patterns)}"])
            track_item.setExpanded(True)
            
        # Add mixing plan
        if session.mixing_plan:
            mp = session.mixing_plan
            mix_item = QTreeWidgetItem(self.data_tree, ["🎛️ Mixing Plan"])
            QTreeWidgetItem(mix_item, [f"Tracks Mixed: {len(mp.track_mixing)}"])
            mix_item.setExpanded(True)
            
    def _on_stage_changed(self, session_id: str, new_stage: str):
        """Handle stage change from agent manager"""
        if session_id != self.session_id:
            return
            
        self.current_stage = new_stage
        self._update_stage_indicator(new_stage)
        
        # Update agent label
        agent_names = {
            "brainstorming": "Brainstorming Agent",
            "producer": "Producer Agent",
            "conductor": "Conductor Agent",
            "track": "Track Agent",
            "mixing": "Mixing & Mastering Agent",
            "complete": "Production Complete"
        }
        
        self.current_agent_label.setText(agent_names.get(new_stage, new_stage.title()))
        self.current_stage_label.setText(f"Stage: {new_stage.title()}")
        
        # Update data panel
        self._update_data_panel()
        
        # Show approval buttons for certain stages
        if new_stage in ["producer", "conductor", "track", "mixing"]:
            self.approval_widget.show()
        else:
            self.approval_widget.hide()
            
    def _on_agent_response(self, session_id: str, response: str):
        """Handle agent response"""
        if session_id != self.session_id:
            return
            
        # Extract agent name from current stage
        agent_names = {
            "brainstorming": "Brainstorming Agent",
            "producer": "Producer Agent",
            "conductor": "Conductor Agent",
            "track": "Track Agent",
            "mixing": "Mixing & Mastering Agent"
        }
        agent_name = agent_names.get(self.current_stage, "AI Agent")
        
        self._add_agent_message(agent_name, response)
        self.status_label.setText(f"{agent_name} responded")
        
        # Update data panel after response
        self._update_data_panel()
        
    def _on_production_complete(self, session_id: str, final_data: dict):
        """Handle production completion"""
        if session_id != self.session_id:
            return
            
        self._add_system_message("🎉 Production complete! Your track has been fully created, mixed, and mastered.")
        self.status_label.setText("Production complete!")
        self.approval_widget.hide()
        
        # Update session info with final data
        info_text = "Production Complete!\n\n"
        info_text += f"Session ID: {session_id}\n"
        if final_data.get("brainstorm"):
            info_text += f"\nGenre: {final_data['brainstorm'].get('genre', 'N/A')}\n"
        if final_data.get("production_plan"):
            pp = final_data['production_plan']
            info_text += f"Tempo: {pp.get('tempo_bpm', 'N/A')} BPM\n"
            info_text += f"Key: {pp.get('key', 'N/A')}\n"
        self.session_info.setPlainText(info_text)
        
    def _on_approve_stage(self):
        """Handle stage approval"""
        if not self.session_id or not self.agent_manager:
            return
            
        response = self.agent_manager.approve_stage(self.session_id)
        self._add_agent_message("System", response)
        self.stage_approved.emit(self.current_stage)
        
    def _on_request_revision(self):
        """Handle revision request"""
        if not self.session_id or not self.agent_manager:
            return
            
        # Get feedback from input field
        feedback = self.input_field.text().strip()
        if not feedback:
            self._add_system_message("Please describe what you'd like changed in the input field, then click Request Changes.")
            return
            
        response = self.agent_manager.revise_stage(self.session_id, feedback)
        self._add_agent_message("System", response)
        self.revision_requested.emit(self.current_stage, feedback)
        self.input_field.clear()
        
    def _add_message(self, sender: str, message: str, is_user: bool = False):
        """Add a message to the chat display"""
        timestamp = time.strftime("%H:%M")
        
        # Format message
        if is_user:
            color = "#4a9eff"
            prefix = "You"
        else:
            color = "#90ee90"
            prefix = sender
            
        html = f"""
        <div style='margin: 5px 0;'>
            <span style='color: #666; font-size: 10px;'>[{timestamp}]</span>
            <span style='color: {color}; font-weight: bold;'>{prefix}:</span>
            <span style='color: #eee;'>{message}</span>
        </div>
        """
        
        self.chat_display.append(html)
        
        # Scroll to bottom
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
        # Store in history
        self.chat_history.append({
            'sender': prefix,
            'message': message,
            'timestamp': timestamp,
            'is_user': is_user
        })
        
    def _add_agent_message(self, agent_name: str, message: str):
        """Add an agent message"""
        self._add_message(agent_name, message, is_user=False)
        
    def _add_system_message(self, message: str):
        """Add a system message"""
        html = f"""
        <div style='margin: 5px 0;'>
            <span style='color: #ffd93d; font-style: italic;'>{message}</span>
        </div>
        """
        self.chat_display.append(html)
        
    def _send_message(self):
        """Send user message"""
        if not self.session_id:
            self._add_system_message("Please start a new session first!")
            return
            
        message = self.input_field.text().strip()
        if not message:
            return
            
        # Add user message
        self._add_message("You", message, is_user=True)
        self.input_field.clear()
        
        # Emit signal
        self.message_sent.emit(message)
        
        # Get AI response
        self._get_ai_response(message)
        
    def _get_ai_response(self, message: str):
        """Get AI response"""
        self.status_label.setText("Thinking...")
        self.send_btn.setEnabled(False)
        
        # Process through agent manager
        if self.agent_manager and self.session_id:
            try:
                response = self.agent_manager.send_message(self.session_id, message)
                # Response will come through the response_received signal
            except Exception as e:
                self._add_system_message(f"Error: {str(e)}")
                self.status_label.setText("Error occurred")
        else:
            # Fallback for when no session
            QTimer.singleShot(500, lambda: self._process_fallback_response(message))
        
        self.send_btn.setEnabled(True)
        
    def _process_fallback_response(self, user_message: str):
        """Process fallback response when no agent manager"""
        # Simple response logic
        responses = {
            'melody': "I can help you create a melody! Start a new session to use the full multi-agent pipeline.",
            'chord': "For chords, start a new session to get structured production help.",
            'drum': "I can create drum patterns! Start a new session to begin.",
            'bass': "A bass line would add great foundation! Start a session to begin.",
        }
        
        response = "Start a new session to begin working with the AI production pipeline!"
        
        msg_lower = user_message.lower()
        for keyword, resp in responses.items():
            if keyword in msg_lower:
                response = resp
                break
                
        self._add_agent_message("AI", response)
        self.status_label.setText("Ready")
        self.send_btn.setEnabled(True)
        
    def _on_suggestion(self, suggestion: str):
        """Handle suggestion button click"""
        self.input_field.setText(suggestion)
        self._send_message()
        
    def _generate_music(self):
        """Generate music based on conversation"""
        if self.is_generating:
            return
            
        if not self.session_id:
            self._add_system_message("Please start a new session first!")
            return
            
        self.is_generating = True
        self.generate_btn.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.status_label.setText("Generating music...")
        
        # Simulate generation progress
        self._simulate_generation()
        
    def _simulate_generation(self):
        """Simulate music generation progress"""
        progress = 0
        
        def update_progress():
            nonlocal progress
            progress += 10
            self.progress_bar.setValue(progress)
            
            if progress < 100:
                QTimer.singleShot(200, update_progress)
            else:
                self._on_generation_complete()
                
        update_progress()
        
    def _on_generation_complete(self):
        """Handle generation completion"""
        self.is_generating = False
        self.generate_btn.setEnabled(True)
        self.progress_bar.hide()
        self.status_label.setText("Generation complete!")
        
        # Add success message
        self._add_system_message("Music generated successfully! Click 'Import Audio' to add it to your project.")
        
        self.import_btn.setEnabled(True)
        
        # Emit signal with placeholder path
        self.music_generated.emit("generated_audio.wav")
        
    def _import_audio(self):
        """Import generated audio to timeline"""
        # In production, this would import the actual generated file
        self._add_system_message("Audio imported to timeline!")
        self.import_btn.setEnabled(False)
        
    def _clear_chat(self):
        """Clear chat history"""
        self.chat_display.clear()
        self.chat_history.clear()
        self._add_system_message("Chat cleared. Start a new session to begin!")
        
    def focus_input(self):
        """Focus the input field"""
        self.input_field.setFocus()
        
    def get_chat_history(self):
        """Get chat history"""
        return self.chat_history
        
    def load_conversation(self, history: list):
        """Load a conversation"""
        self.chat_history = history
        self.chat_display.clear()
        
        for entry in history:
            self._add_message(
                entry['sender'],
                entry['message'],
                is_user=entry.get('is_user', entry['sender'] == 'You')
            )
            
    def get_session_id(self) -> str:
        """Get current session ID"""
        return self.session_id
        
    def set_session_id(self, session_id: str):
        """Set session ID (for loading saved sessions)"""
        self.session_id = session_id
        if self.agent_manager and session_id:
            session = self.agent_manager.get_session(session_id)
            if session:
                self.current_stage = session.current_stage.value
                self._update_stage_indicator(self.current_stage)
                self._update_data_panel()
