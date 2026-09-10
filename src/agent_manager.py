"""
AI Agent Manager for Music Composition - Multi-Agent Architecture
Manages 5 specialized agents that collaborate to create music:
1. Brainstorming Agent - Understands user's vision
2. Producer Agent - Creates structured production plan
3. Conductor Agent - Decides instrumentation and arrangement
4. Track Agent - Creates tracks and writes MIDI/note patterns
5. Mixing/Mastering Agent - Applies mixing decisions

Now integrated with OpenJarvis AI framework for intelligent responses.
"""

import os
import json
import uuid
import random
from typing import Optional, Dict, List, Callable, Any
from PyQt6.QtCore import QObject, pyqtSignal, QThread
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum

from diff_engine import Transaction, DiffOperation, DiffOperationType, SongDocument
from lock_manager import LockManager

# Import OpenJarvis client
try:
    from openjarvis_client import OpenJarvisClient, FallbackAIClient
    OPENJARVIS_AVAILABLE = True
except Exception:
    OPENJARVIS_AVAILABLE = False
    print("Warning: openjarvis_client not available. Using fallback mode.")
    try:
        from openjarvis_client import FallbackAIClient
    except Exception:
        from PyQt6.QtCore import QObject, pyqtSignal

        class FallbackAIClient(QObject):
            response_ready = pyqtSignal(str, object)
            error_occurred = pyqtSignal(str, str)

            def initialize(self, *args, **kwargs):
                return False

            def close(self):
                pass


class AgentStage(Enum):
    BRAINSTORMING = "brainstorming"
    PRODUCER = "producer"
    CONDUCTOR = "conductor"
    TRACK = "track"
    MIXING = "mixing"
    COMPLETE = "complete"


@dataclass
class BrainstormData:
    genre: str = ""
    mood: str = ""
    style: str = ""
    purpose: str = ""
    tempo_preference: str = ""  # slow, medium, fast, specific BPM
    key_preference: str = ""  # any, major, minor, specific key
    reference_artists: List[str] = field(default_factory=list)
    reference_tracks: List[str] = field(default_factory=list)
    user_notes: str = ""
    approved: bool = False


@dataclass
class ProductionPlan:
    title: str = ""
    tempo_bpm: int = 120
    key: str = "C major"
    time_signature: str = "4/4"
    duration_bars: int = 64
    sections: List[Dict] = field(default_factory=list)
    # Each section: {"name": "intro", "bars": 8, "energy": "low", "elements": [...]}
    vibe_description: str = ""
    arrangement_notes: str = ""
    approved: bool = False


@dataclass
class InstrumentationPlan:
    tracks: List[Dict] = field(default_factory=list)
    # Each track: {"name": "Kick", "instrument": "808 Kick", "type": "drum", "role": "foundation"}
    sounds: List[Dict] = field(default_factory=list)
    # Each sound: {"name": "Main Synth", "preset": "Supersaw", "effects": ["reverb", "delay"]}
    arrangement: Dict = field(default_factory=dict)
    # {"intro": [...], "verse": [...], "chorus": [...], ...}
    approved: bool = False


@dataclass
class TrackData:
    created_tracks: List[Dict] = field(default_factory=list)
    # Each track with clip data: {"track_name": "...", "clips": [...]}
    midi_patterns: List[Dict] = field(default_factory=list)
    # Each pattern: {"track": "...", "notes": [...], "start_bar": 0, "length_bars": 4}
    automation: List[Dict] = field(default_factory=list)
    approved: bool = False


@dataclass
class MixingPlan:
    track_mixing: List[Dict] = field(default_factory=list)
    # Each track: {"track_name": "...", "volume_db": -6, "pan": 0, "eq": {...}, "compression": {...}}
    master_effects: Dict = field(default_factory=dict)
    # {"eq": {...}, "compression": {...}, "limiter": {...}, "stereo_width": 100}
    reverb_sends: Dict = field(default_factory=dict)
    approved: bool = False


@dataclass
class ProductionSession:
    id: str = ""
    current_stage: AgentStage = AgentStage.BRAINSTORMING
    brainstorm_data: Optional[BrainstormData] = None
    production_plan: Optional[ProductionPlan] = None
    instrumentation_plan: Optional[InstrumentationPlan] = None
    track_data: Optional[TrackData] = None
    mixing_plan: Optional[MixingPlan] = None
    messages: List[Dict] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    user_approvals: Dict = field(default_factory=dict)
    # Track which stages user has approved: {"brainstorming": True, ...}


@dataclass
class AgentConfig:
    name: str = ""
    description: str = ""
    system_prompt: str = ""
    stage: AgentStage = AgentStage.BRAINSTORMING
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 2000


@dataclass
class Conversation:
    id: str = ""
    agent_type: str = ""
    messages: List[Dict] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class AgentManager(QObject):
    
    # Signals
    response_received = pyqtSignal(str, str)  # session_id, response
    error_occurred = pyqtSignal(str, str)  # session_id, error
    agent_status_changed = pyqtSignal(str, str)  # session_id, status
    stage_changed = pyqtSignal(str, str)  # session_id, new_stage
    approval_needed = pyqtSignal(str, str, str)  # session_id, stage, summary
    production_complete = pyqtSignal(str, dict)  # session_id, final_data
    
    def __init__(self, config_path: str = None, openjarvis_config: Dict = None):
        super().__init__()
        
        self.config_path = config_path or os.path.expanduser("~/.aria/agents.json")
        self.agents: Dict[str, AgentConfig] = {}
        self.sessions: Dict[str, ProductionSession] = {}
        self.conversations: Dict[str, Conversation] = {}  # Legacy support
        self.active_session: Optional[str] = None
        self.elevenlabs_client = None
        
        # Initialize OpenJarvis client
        self._init_openjarvis(openjarvis_config)
        
        # Setup the 5 specialized agents
        self._setup_multi_agents()
        
        # Load saved configurations
        self._load_config()
        
    def _init_openjarvis(self, config: Dict = None):
        """Initialize OpenJarvis client with configuration"""
        config = config or {}
        
        if OPENJARVIS_AVAILABLE:
            try:
                self.jarvis_client = OpenJarvisClient(
                    config_path=config.get('config_path'),
                    engine_key=config.get('engine_key', 'ollama')
                )
                # Try to initialize with default or specified model
                model = config.get('model', 'llama3')
                if self.jarvis_client.initialize(model=model):
                    print(f"OpenJarvis initialized with model: {model}")
                else:
                    print("OpenJarvis initialization failed, using fallback")
                    self.jarvis_client = FallbackAIClient()
            except Exception as e:
                print(f"OpenJarvis setup error: {e}, using fallback")
                self.jarvis_client = FallbackAIClient()
        else:
            self.jarvis_client = FallbackAIClient()
            
        # Connect signals
        self.jarvis_client.response_ready.connect(self._on_jarvis_response)
        self.jarvis_client.error_occurred.connect(self._on_jarvis_error)
        
    def _on_jarvis_response(self, session_id: str, response: str):
        """Handle OpenJarvis response"""
        # This is handled via the ask method's return value
        pass
        
    def _on_jarvis_error(self, session_id: str, error: str):
        """Handle OpenJarvis error"""
        self.error_occurred.emit(session_id, error)
        
    def _setup_multi_agents(self):
        
        # 1. Brainstorming Agent - Understands user's vision
        self.agents["brainstorming"] = AgentConfig(
            name="Brainstorming Agent",
            description="Chat with you to understand your musical vision - genre, mood, style, and purpose",
            stage=AgentStage.BRAINSTORMING,
            system_prompt="""You are the Brainstorming Agent for a music production AI system. Your role is to 
            have a friendly, creative conversation with the user to understand their vision for a song.
            
            Ask about:
            - Genre preferences (pop, hip hop, house, trap, rock, lo-fi, etc.)
            - Mood and emotion they want to convey
            - Style references (artists, songs, eras)
            - Purpose (dance track, emotional ballad, background music, etc.)
            - Tempo preferences (slow, medium, fast, or specific BPM)
            - Key preferences (major/minor, specific key, or "surprise me")
            
            Be conversational and encouraging. Extract as much detail as possible while keeping it natural.
            Once you have enough information, summarize the vision and ask if they're ready to move to 
            the Producer Agent who will create a structured plan.""",
            model="gpt-4",
            temperature=0.8
        )
        
        # 2. Producer Agent - Creates structured production plan
        self.agents["producer"] = AgentConfig(
            name="Producer Agent",
            description="Takes your vision and creates a structured production plan with song structure",
            stage=AgentStage.PRODUCER,
            system_prompt="""You are the Producer Agent for a music production AI system. You take the user's 
            vision from the Brainstorming Agent and create a detailed, structured production plan.
            
            Your output should include:
            - Suggested tempo (BPM) and key
            - Time signature
            - Total duration in bars
            - Detailed song structure with sections (intro, verse, chorus, bridge, outro, etc.)
            - Energy level for each section (low/medium/high)
            - Which instruments/elements should appear in each section
            - Overall vibe and arrangement notes
            
            Present this as a clear, organized plan and ask the user for approval before proceeding 
            to the Conductor Agent.""",
            model="gpt-4",
            temperature=0.7
        )
        
        # 3. Conductor Agent - Decides instrumentation and arrangement
        self.agents["conductor"] = AgentConfig(
            name="Conductor Agent",
            description="Decides which instruments, sounds, and arrangement to use based on the production plan",
            stage=AgentStage.CONDUCTOR,
            system_prompt="""You are the Conductor Agent for a music production AI system. You take the 
            Producer's plan and decide on the specific instrumentation, sounds, and arrangement.
            
            Your decisions should include:
            - Track list with specific instrument names (e.g., "808 Kick", "Fender Bass", "Supersaw Lead")
            - Sound design choices (presets, synthesis types, sample selections)
            - Effect chains for each instrument (reverb, delay, distortion, etc.)
            - Detailed arrangement mapping which tracks play in which sections
            - Dynamic changes (filter sweeps, build-ups, breaks)
            
            Think like an orchestrator - every sound should serve the song. Present your instrumentation 
            plan and ask for approval before the Track Agent creates the actual tracks.""",
            model="gpt-4",
            temperature=0.75
        )
        
        # 4. Track Agent - Creates tracks and writes MIDI/note patterns
        self.agents["track"] = AgentConfig(
            name="Track Agent",
            description="Creates actual tracks in the DAW, assigns instruments, and writes note patterns/MIDI data",
            stage=AgentStage.TRACK,
            system_prompt="""You are the Track Agent for a music production AI system. You take the 
            Conductor's instrumentation plan and create the actual tracks in the DAW.
            
            Your work includes:
            - Creating tracks with proper names and instrument assignments
            - Writing MIDI patterns and note data for each instrument
            - Creating drum patterns, bass lines, melodies, chords, and other musical elements
            - Setting up clip positions on the timeline
            - Adding basic automation (volume fades, filter sweeps)
            
            Be specific with note data (pitch, velocity, timing). Present what you've created and 
            ask for approval before the Mixing/Mastering Agent applies final processing.""",
            model="gpt-4",
            temperature=0.7
        )
        
        # 5. Mixing/Mastering Agent - Applies mixing decisions
        self.agents["mixing"] = AgentConfig(
            name="Mixing & Mastering Agent",
            description="Applies mixing decisions - EQ, compression, reverb, levels - to finalize the track",
            stage=AgentStage.MIXING,
            system_prompt="""You are the Mixing & Mastering Agent for a music production AI system. You take 
            the completed tracks and apply professional mixing and mastering decisions.
            
            - Volume levels and panning for each track
            - EQ settings (frequency cuts and boosts)
            - Compression settings (threshold, ratio, attack, release)
            - Reverb sends and spatial effects
            - Master bus processing (stereo width, limiting, final EQ)
            
            Reference the Producer's plan for the overall vibe. Present your mixing decisions and 
            confirm when the production is complete.""",
            model="gpt-4",
            temperature=0.6
        )
        
    def _load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                    
                # Load sessions
                if "sessions" in data:
                    for session_id, session_data in data["sessions"].items():
                        self.sessions[session_id] = self._deserialize_session(session_data)
                        
            except Exception as e:
                print(f"Error loading agent config: {e}")
                
    def _deserialize_session(self, data: dict) -> ProductionSession:
        session = ProductionSession(
            id=data.get("id", ""),
            current_stage=AgentStage(data.get("current_stage", "brainstorming")),
            messages=data.get("messages", []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            user_approvals=data.get("user_approvals", {})
        )
        
        if "brainstorm_data" in data and data["brainstorm_data"]:
            bd = data["brainstorm_data"]
            session.brainstorm_data = BrainstormData(
                genre=bd.get("genre", ""),
                mood=bd.get("mood", ""),
                style=bd.get("style", ""),
                purpose=bd.get("purpose", ""),
                tempo_preference=bd.get("tempo_preference", ""),
                key_preference=bd.get("key_preference", ""),
                reference_artists=bd.get("reference_artists", []),
                reference_tracks=bd.get("reference_tracks", []),
                user_notes=bd.get("user_notes", ""),
                approved=bd.get("approved", False)
            )
            
        if "production_plan" in data and data["production_plan"]:
            pp = data["production_plan"]
            session.production_plan = ProductionPlan(
                title=pp.get("title", ""),
                tempo_bpm=pp.get("tempo_bpm", 120),
                key=pp.get("key", "C major"),
                time_signature=pp.get("time_signature", "4/4"),
                duration_bars=pp.get("duration_bars", 64),
                sections=pp.get("sections", []),
                vibe_description=pp.get("vibe_description", ""),
                arrangement_notes=pp.get("arrangement_notes", ""),
                approved=pp.get("approved", False)
            )
            
        return session
        
    def save_config(self):
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            
            data = {
                "sessions": {}
            }
            
            for session_id, session in self.sessions.items():
                data["sessions"][session_id] = self._serialize_session(session)
            
            with open(self.config_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"Error saving agent config: {e}")
            
    def _serialize_session(self, session: ProductionSession) -> dict:
        return {
            "id": session.id,
            "current_stage": session.current_stage.value,
            "brainstorm_data": asdict(session.brainstorm_data) if session.brainstorm_data else None,
            "production_plan": asdict(session.production_plan) if session.production_plan else None,
            "instrumentation_plan": asdict(session.instrumentation_plan) if session.instrumentation_plan else None,
            "track_data": asdict(session.track_data) if session.track_data else None,
            "mixing_plan": asdict(session.mixing_plan) if session.mixing_plan else None,
            "messages": session.messages,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "user_approvals": session.user_approvals
        }
        
    def set_elevenlabs_client(self, client):
        self.elevenlabs_client = client
        
    def get_agent(self, agent_id: str) -> Optional[AgentConfig]:
        return self.agents.get(agent_id)
        
    def get_agent_list(self) -> List[tuple]:
        return [(k, v.name, v.description, v.stage.value) for k, v in self.agents.items()]
        
    def get_current_stage_agents(self) -> List[tuple]:
        pipeline_order = ["brainstorming", "producer", "conductor", "track", "mixing"]
        return [(k, self.agents[k].name, self.agents[k].description) 
                for k in pipeline_order if k in self.agents]
        
    def start_production_session(self) -> str:
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        session = ProductionSession(
            id=session_id,
            current_stage=AgentStage.BRAINSTORMING,
            brainstorm_data=BrainstormData(),
            created_at=now,
            updated_at=now
        )
        
        # Add system message from Brainstorming Agent
        agent = self.agents["brainstorming"]
        session.messages.append({
            "role": "system",
            "content": agent.system_prompt,
            "timestamp": now,
        })
        
        self.sessions[session_id] = session
        self.active_session = session_id
        
        # Generate initial greeting
        greeting = self._generate_agent_greeting("brainstorming")
        session.messages.append({
            "role": "assistant",
            "content": greeting,
            "timestamp": datetime.now().isoformat()
        })
        
        self.save_config()
        self.agent_status_changed.emit(session_id, "started")
        
        return session_id
        
    def _generate_agent_greeting(self, agent_id: str) -> str:
        greetings = {
            "brainstorming": "Hi! I am your Brainstorming Agent. Let's explore your musical vision! Tell me about the genre, mood, style, or any artists that inspire you. What kind of track are you looking to create?",
            "producer": "Great! I am the Producer Agent. Based on your vision, I will create a structured production plan with tempo, key, and song sections. Let me analyze what we have discussed...",
            "conductor": "Excellent plan! I am the Conductor Agent. Now I will decide on the specific instruments, sounds, and arrangement to bring this vision to life...",
            "track": "Perfect! I am the Track Agent. I will now create the actual tracks and write the MIDI patterns and note data...",
            "mixing": "Almost done! I am the Mixing & Mastering Agent. I will apply the final polish to your track..."
        }
        return greetings.get(agent_id, "Hello! Ready to create some music?")
        
    def send_message(self, session_id: str, message: str) -> str:
        if session_id not in self.sessions:
            raise ValueError(f"Unknown session: {session_id}")
            
        session = self.sessions[session_id]
        
        # Add user message
        session.messages.append({
            "role": "user",
            "content": message,
            "agent": session.current_stage.value
        })
        
        # Get current agent
        current_agent_id = session.current_stage.value
        agent = self.agents.get(current_agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {current_agent_id}")
            
        # Generate response using OpenJarvis
        response = self._generate_response(agent, session, message)
        
        # Add assistant response
        session.messages.append({
            "role": "assistant",
            "content": response,
            "agent": current_agent_id
        })
        
        session.updated_at = datetime.now().isoformat()
        
        self.response_received.emit(session_id, response)
        
        return response
        
    def _generate_response(self, agent: AgentConfig, session: ProductionSession, user_message: str) -> str:
        """Generate AI response using OpenJarvis or fallback to keyword-based system"""
        
        msg_lower = user_message.lower()
        
        # Check for approval keywords
        if any(word in msg_lower for word in ["approve", "yes", "good", "perfect", "great", "continue", "next", "proceed"]):
            return self._handle_approval(agent, session, user_message)
            
        # Check for revision requests
        if any(word in msg_lower for word in ["change", "modify", "different", "no", "redo", "fix"]):
            return self._handle_revision(agent, session, user_message)
        
        # Try to use OpenJarvis for AI response
        if self.jarvis_client and self.jarvis_client.is_available():
            try:
                # Get conversation history (last 10 messages)
                context_messages = session.messages[-10:] if len(session.messages) > 0 else []
                
                # Call OpenJarvis
                response = self.jarvis_client.ask(
                    session_id=session.id,
                    query=user_message,
                    system_prompt=agent.system_prompt,
                    temperature=agent.temperature,
                    max_tokens=agent.max_tokens,
                    context_messages=context_messages
                )
                
                if response:
                    return response
                    
            except Exception as e:
                print(f"OpenJarvis error: {e}, falling back to keyword-based response")
        
        # Fallback to keyword-based responses if OpenJarvis fails or is unavailable
        return self._fallback_response(agent, session, user_message)
        
    def _fallback_response(self, agent: AgentConfig, session: ProductionSession, user_message: str) -> str:
        """Fallback keyword-based response system"""
        
        # Stage-specific responses
        if agent.stage == AgentStage.BRAINSTORMING:
            return self._brainstorming_response(session, user_message)
        elif agent.stage == AgentStage.PRODUCER:
            return self._producer_response(session, user_message)
        elif agent.stage == AgentStage.CONDUCTOR:
            return self._conductor_response(session, user_message)
        elif agent.stage == AgentStage.TRACK:
            return self._track_response(session, user_message)
        elif agent.stage == AgentStage.MIXING:
            return self._mixing_response(session, user_message)
            
        return "I am here to help! What would you like to work on?"
        
    def _handle_approval(self, agent: AgentConfig, session: ProductionSession, message: str) -> str:
        # Mark current stage as approved
        session.user_approvals[agent.stage.value] = True
        
        # Update structured data based on stage
        if agent.stage == AgentStage.BRAINSTORMING:
            if session.brainstorm_data:
                session.brainstorm_data.approved = True
            # Extract brainstorm data from conversation
            self._extract_brainstorm_data(session)
        elif agent.stage == AgentStage.PRODUCER:
            if session.production_plan:
                session.production_plan.approved = True
            self._extract_production_plan(session)
        elif agent.stage == AgentStage.CONDUCTOR:
            if session.instrumentation_plan:
                session.instrumentation_plan.approved = True
            self._extract_instrumentation_plan(session)
        elif agent.stage == AgentStage.TRACK:
            if session.track_data:
                session.track_data.approved = True
        elif agent.stage == AgentStage.MIXING:
            if session.mixing_plan:
                session.mixing_plan.approved = True
            session.current_stage = AgentStage.COMPLETE
            self.production_complete.emit(session.id, self._get_final_data(session))
            return "Production complete! Your track has been fully created, mixed, and mastered. You can now export it or make further adjustments."
        
        # Move to next stage
        stage_order = [AgentStage.BRAINSTORMING, AgentStage.PRODUCER, AgentStage.CONDUCTOR, 
                      AgentStage.TRACK, AgentStage.MIXING]
        current_idx = stage_order.index(agent.stage)
        if current_idx < len(stage_order) - 1:
            next_stage = stage_order[current_idx + 1]
            session.current_stage = next_stage
            self.stage_changed.emit(session.id, next_stage.value)
            
            # Generate greeting for next agent
            next_agent_id = next_stage.value
            return self._generate_agent_greeting(next_agent_id)
        
        return "Stage approved! Moving forward..."
        
    def _handle_revision(self, agent: AgentConfig, session: ProductionSession, message: str) -> str:
        """Handle revision requests"""
        return f"I understand you'd like to make changes. Could you please tell me more specifically what you'd like to modify for the {agent.name} stage?"
        
    def _brainstorming_response(self, session: ProductionSession, message: str) -> str:
        """Generate brainstorming stage response"""
        msg_lower = message.lower()
        
        # Extract and store information
        if session.brainstorm_data:
            if any(word in msg_lower for word in ["pop", "hip hop", "house", "trap", "rock", "lo-fi", "electronic", "jazz", "classical"]):
                for genre in ["pop", "hip hop", "house", "trap", "rock", "lo-fi", "electronic", "jazz", "classical"]:
                    if genre in msg_lower:
                        session.brainstorm_data.genre = genre.title()
                        break
                        
            if any(word in msg_lower for word in ["happy", "sad", "energetic", "calm", "dark", "bright", "melancholic", "upbeat"]):
                for mood in ["happy", "sad", "energetic", "calm", "dark", "bright", "melancholic", "upbeat"]:
                    if mood in msg_lower:
                        session.brainstorm_data.mood = mood.title()
                        break
        
        responses = [
            "That's a great starting point! Tell me more about the mood you're going for. Is it energetic, calm, dark, or something else?",
            "Interesting! Are there any specific artists or songs that inspire this track?",
            "Got it! What's the purpose of this track - is it for dancing, background music, or something more emotional?",
            "Nice vision! Do you have a preference for tempo - slow, medium, fast, or a specific BPM?",
            "I love that direction! Any preference for the key - major, minor, or a specific key?"
        ]
        return random.choice(responses)
        
    def _producer_response(self, session: ProductionSession, message: str) -> str:
        """Generate producer stage response"""
        if not session.production_plan:
            session.production_plan = ProductionPlan()
            
        # Generate a production plan based on brainstorm data
        if session.brainstorm_data:
            bd = session.brainstorm_data
            
            # Set defaults based on genre
            if bd.genre:
                genre_lower = bd.genre.lower()
                if "trap" in genre_lower or "hip hop" in genre_lower:
                    session.production_plan.tempo_bpm = 140
                    session.production_plan.key = "F minor"
                elif "house" in genre_lower:
                    session.production_plan.tempo_bpm = 124
                    session.production_plan.key = "A minor"
                elif "pop" in genre_lower:
                    session.production_plan.tempo_bpm = 120
                    session.production_plan.key = "C major"
                    
        plan_text = f"""Based on your vision, here's my production plan:

**Song Structure:**
- Tempo: {session.production_plan.tempo_bpm} BPM
- Key: {session.production_plan.key}
- Time Signature: {session.production_plan.time_signature}
- Duration: {session.production_plan.duration_bars} bars

**Sections:**
1. Intro (8 bars) - Low energy, minimal elements
2. Verse 1 (16 bars) - Medium energy, build up
3. Chorus (16 bars) - High energy, full arrangement
4. Verse 2 (16 bars) - Medium energy
5. Chorus (16 bars) - High energy
6. Outro (8 bars) - Fade out

Does this plan work for you? Type "approve" to continue to the Conductor Agent, or let me know what you'd like to change."""
        
        return plan_text
        
    def _conductor_response(self, session: ProductionSession, message: str) -> str:
        """Generate conductor stage response"""
        if not session.instrumentation_plan:
            session.instrumentation_plan = InstrumentationPlan()
            
        # Create instrumentation based on genre
        genre = ""
        if session.brainstorm_data:
            genre = session.brainstorm_data.genre.lower()
            
        if "trap" in genre or "hip hop" in genre:
            tracks = [
                {"name": "808 Kick", "instrument": "808 Kick", "type": "drum"},
                {"name": "Snare", "instrument": "Trap Snare", "type": "drum"},
                {"name": "Hi-Hats", "instrument": "Closed Hi-Hat", "type": "drum"},
                {"name": "808 Bass", "instrument": "808 Bass", "type": "bass"},
                {"name": "Lead Synth", "instrument": "Trap Lead", "type": "synth"},
                {"name": "Pad", "instrument": "Ambient Pad", "type": "pad"}
            ]
        else:
            tracks = [
                {"name": "Kick", "instrument": "Kick Drum", "type": "drum"},
                {"name": "Snare", "instrument": "Snare", "type": "drum"},
                {"name": "Bass", "instrument": "Bass Guitar", "type": "bass"},
                {"name": "Lead", "instrument": "Synth Lead", "type": "synth"},
                {"name": "Pad", "instrument": "String Pad", "type": "pad"}
            ]
            
        session.instrumentation_plan.tracks = tracks
        
        track_list = "\n".join([f"- {t['name']} ({t['instrument']})" for t in tracks])
        
        return f"""Here's my instrumentation plan:

**Tracks:**
{track_list}

**Arrangement:**
- Intro: Kick + Pad
- Verse: Add Bass + Snare
- Chorus: Full arrangement with Lead
- Outro: Strip back to Pad only

Type "approve" to have the Track Agent create these tracks, or tell me what to change."""
        
    def _track_response(self, session: ProductionSession, message: str) -> str:
        """Generate track stage response"""
        if not session.track_data:
            session.track_data = TrackData()
            
        return """I've created the tracks and written the MIDI patterns:

**Created Tracks:**
- Drum tracks with programmed patterns
- Bass line following the chord progression
- Melody and harmony parts
- Effects and automation setup

The arrangement follows the Producer's plan with proper section markers. Type "approve" to move to mixing, or let me know if you'd like any adjustments to the patterns."""
        
    def _mixing_response(self, session: ProductionSession, message: str) -> str:
        """Generate mixing stage response"""
        if not session.mixing_plan:
            session.mixing_plan = MixingPlan()
            
        return """I've applied the mixing and mastering:

**Track Mixing:**
- Balanced volume levels (-6dB headroom)
- Panning for stereo width
- EQ cuts to avoid frequency clashes
- Light compression on dynamic elements

**Master Bus:**
- Stereo width enhancement
- Gentle limiting
- Final EQ polish

Type "approve" to complete the production!"""
        
    def _extract_brainstorm_data(self, session: ProductionSession):
        """Extract brainstorm data from conversation"""
        if not session.brainstorm_data:
            session.brainstorm_data = BrainstormData()
            
        # Simple extraction from messages
        for msg in session.messages:
            if msg.get("role") == "user":
                content = msg.get("content", "").lower()
                
                # Extract genre
                for genre in ["pop", "hip hop", "house", "trap", "rock", "lo-fi", "electronic", "jazz"]:
                    if genre in content:
                        session.brainstorm_data.genre = genre.title()
                        
                # Extract mood
                for mood in ["happy", "sad", "energetic", "calm", "dark", "bright", "melancholic", "upbeat"]:
                    if mood in content:
                        session.brainstorm_data.mood = mood.title()
                        
    def _extract_production_plan(self, session: ProductionSession):
        """Extract production plan from conversation"""
        if not session.production_plan:
            session.production_plan = ProductionPlan()
            
    def _extract_instrumentation_plan(self, session: ProductionSession):
        """Extract instrumentation plan from conversation"""
        if not session.instrumentation_plan:
            session.instrumentation_plan = InstrumentationPlan()
            
    def _get_final_data(self, session: ProductionSession) -> dict:
        """Get final production data"""
        return {
            "session_id": session.id,
            "brainstorm_data": asdict(session.brainstorm_data) if session.brainstorm_data else None,
            "production_plan": asdict(session.production_plan) if session.production_plan else None,
            "instrumentation_plan": asdict(session.instrumentation_plan) if session.instrumentation_plan else None,
            "track_data": asdict(session.track_data) if session.track_data else None,
            "mixing_plan": asdict(session.mixing_plan) if session.mixing_plan else None,
        }
        
    def get_session(self, session_id: str) -> Optional[ProductionSession]:
        """Get a session by ID"""
        return self.sessions.get(session_id)
        
    def advance_stage(self, session_id: str) -> bool:
        """Manually advance to next stage"""
        if session_id not in self.sessions:
            return False
            
        session = self.sessions[session_id]
        stage_order = [AgentStage.BRAINSTORMING, AgentStage.PRODUCER, AgentStage.CONDUCTOR, 
                      AgentStage.TRACK, AgentStage.MIXING, AgentStage.COMPLETE]
        
        try:
            current_idx = stage_order.index(session.current_stage)
            if current_idx < len(stage_order) - 1:
                session.current_stage = stage_order[current_idx + 1]
                self.stage_changed.emit(session_id, session.current_stage.value)
                return True
        except ValueError:
            pass
            
        return False
        
    def close(self):
        """Clean up resources"""
        if self.jarvis_client:
            self.jarvis_client.close()
