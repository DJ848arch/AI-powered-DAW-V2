"""
OpenJarvis Client Wrapper for ARIA DAW
Wraps the OpenJarvis SDK to provide AI conversation capabilities with music production context.
"""

from __future__ import annotations

import os
from typing import Optional, Dict, List, Any, Callable
from dataclasses import dataclass
from PyQt6.QtCore import QObject, pyqtSignal, QThread

# Import OpenJarvis
try:
    from openjarvis import Jarvis
    OPENJARVIS_AVAILABLE = True
except ImportError:
    OPENJARVIS_AVAILABLE = False
    print("Warning: openjarvis package not available. AI features will be limited.")


@dataclass
class JarvisResponse:
    """Response from OpenJarvis"""
    content: str
    model: str = ""
    engine: str = ""
    usage: Optional[Dict] = None


class OpenJarvisClient(QObject):
    """Client for OpenJarvis AI interactions"""
    
    # Signals
    response_ready = pyqtSignal(str, object)  # session_id, response_text
    error_occurred = pyqtSignal(str, str)  # session_id, error_message
    streaming_token = pyqtSignal(str, str)  # session_id, token
    
    def __init__(self, config_path: Optional[str] = None, engine_key: Optional[str] = None):
        super().__init__()
        
        self.config_path = config_path
        self.engine_key = engine_key
        self.jarvis: Optional[Jarvis] = None
        self._initialized = False
        
        # Music production context template
        self.music_context = """You are an AI music production assistant integrated into ARIA, a Digital Audio Workstation (DAW).
You help users create music through a multi-agent pipeline with these stages:
1. Brainstorming - Understanding the user's musical vision
2. Producer - Creating structured production plans
3. Conductor - Deciding instrumentation and arrangement
4. Track - Creating tracks and writing MIDI patterns
5. Mixing - Applying mixing and mastering decisions

When responding:
- Be creative and encouraging about music production
- Provide specific, actionable advice
- Reference music theory, production techniques, and DAW features when relevant
- Ask clarifying questions to better understand the user's vision
- Suggest concrete next steps in the production process

Current DAW Context: ARIA DAW with support for MIDI, audio tracks, effects, and mixing."""
        
    def initialize(self, model: Optional[str] = None) -> bool:
        """Initialize the OpenJarvis client"""
        if not OPENJARVIS_AVAILABLE:
            self.error_occurred.emit("global", "OpenJarvis package not installed")
            return False
            
        try:
            kwargs = {}
            if self.config_path:
                kwargs['config_path'] = self.config_path
            if self.engine_key:
                kwargs['engine_key'] = self.engine_key
            if model:
                kwargs['model'] = model
                
            self.jarvis = Jarvis(**kwargs)
            self._initialized = True
            return True
            
        except Exception as e:
            self.error_occurred.emit("global", f"Failed to initialize OpenJarvis: {str(e)}")
            return False
            
    def is_available(self) -> bool:
        """Check if OpenJarvis is available and initialized"""
        return OPENJARVIS_AVAILABLE and self._initialized and self.jarvis is not None
        
    def list_engines(self) -> List[str]:
        """List available AI engines"""
        if not self.is_available():
            return []
        try:
            return self.jarvis.list_engines()
        except:
            return []
            
    def list_models(self) -> List[str]:
        """List available models"""
        if not self.is_available():
            return []
        try:
            return self.jarvis.list_models()
        except:
            return []
            
    def ask(self, session_id: str, query: str, system_prompt: Optional[str] = None,
            temperature: float = 0.7, max_tokens: int = 2000,
            context_messages: Optional[List[Dict]] = None) -> Optional[str]:
        """Send a query to OpenJarvis and get response"""
        if not self.is_available():
            self.error_occurred.emit(session_id, "OpenJarvis not initialized")
            return None
            
        try:
            # Build conversation context
            full_prompt = self._build_prompt(query, system_prompt, context_messages)
            
            # Call OpenJarvis
            response = self.jarvis.ask(
                full_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                context=True
            )
            
            self.response_ready.emit(session_id, response)
            return response
            
        except Exception as e:
            self.error_occurred.emit(session_id, f"OpenJarvis error: {str(e)}")
            return None
            
    def ask_async(self, session_id: str, query: str, system_prompt: Optional[str] = None,
                  temperature: float = 0.7, max_tokens: int = 2000,
                  context_messages: Optional[List[Dict]] = None):
        """Send query asynchronously using QThread"""
        if not self.is_available():
            self.error_occurred.emit(session_id, "OpenJarvis not initialized")
            return
            
        self._worker = JarvisWorker(
            self.jarvis, session_id, query, system_prompt,
            temperature, max_tokens, context_messages
        )
        self._worker.response_ready.connect(self._on_worker_response)
        self._worker.error_occurred.connect(self._on_worker_error)
        self._worker.start()
        
    def _on_worker_response(self, session_id: str, response: str):
        """Handle worker response"""
        self.response_ready.emit(session_id, response)
        
    def _on_worker_error(self, session_id: str, error: str):
        """Handle worker error"""
        self.error_occurred.emit(session_id, error)
        
    def _build_prompt(self, query: str, system_prompt: Optional[str] = None,
                      context_messages: Optional[List[Dict]] = None) -> str:
        """Build the full prompt with context"""
        parts = []
        
        # Add base music context
        parts.append(self.music_context)
        
        # Add custom system prompt if provided
        if system_prompt:
            parts.append(f"\n\nAgent Instructions:\n{system_prompt}")
            
        # Add conversation history
        if context_messages:
            parts.append("\n\nConversation History:")
            for msg in context_messages[-10:]:  # Keep last 10 messages
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                parts.append(f"{role}: {content}")
                
        # Add current query
        parts.append(f"\n\nUser: {query}")
        parts.append("\nAssistant:")
        
        return "\n".join(parts)
        
    def close(self):
        """Close the OpenJarvis client"""
        if self.jarvis:
            try:
                self.jarvis.close()
            except:
                pass
            self.jarvis = None
            self._initialized = False
            
    def __enter__(self):
        return self
        
    def __exit__(self, *exc):
        self.close()


class JarvisWorker(QThread):
    """Worker thread for async OpenJarvis calls"""
    
    response_ready = pyqtSignal(str, str)  # session_id, response
    error_occurred = pyqtSignal(str, str)  # session_id, error
    
    def __init__(self, jarvis: "Jarvis", session_id: str, query: str,
                 system_prompt: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 2000,
                 context_messages: Optional[List[Dict]] = None):
        super().__init__()
        self.jarvis = jarvis
        self.session_id = session_id
        self.query = query
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.context_messages = context_messages or []
        
    def run(self):
        """Execute the OpenJarvis call"""
        try:
            # Build prompt with context
            parts = []
            parts.append("You are an AI music production assistant integrated into ARIA DAW.")
            
            if self.system_prompt:
                parts.append(f"\nAgent Instructions:\n{self.system_prompt}")
                
            if self.context_messages:
                parts.append("\nConversation History:")
                for msg in self.context_messages[-10:]:
                    role = msg.get('role', 'user')
                    content = msg.get('content', '')
                    parts.append(f"{role}: {content}")
                    
            parts.append(f"\nUser: {self.query}")
            parts.append("\nAssistant:")
            
            full_prompt = "\n".join(parts)
            
            response = self.jarvis.ask(
                full_prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                context=True
            )
            
            self.response_ready.emit(self.session_id, response)
            
        except Exception as e:
            self.error_occurred.emit(self.session_id, str(e))


# Fallback client for when OpenJarvis is not available
class FallbackAIClient(QObject):
    """Fallback AI client that provides basic responses when OpenJarvis is unavailable"""
    
    response_ready = pyqtSignal(str, object)
    error_occurred = pyqtSignal(str, str)
    
    def __init__(self):
        super().__init__()
        
    def is_available(self) -> bool:
        return True
        
    def ask(self, session_id: str, query: str, system_prompt: Optional[str] = None,
            temperature: float = 0.7, max_tokens: int = 2000,
            context_messages: Optional[List[Dict]] = None) -> str:
        """Provide a fallback response"""
        response = ("I'm currently running in fallback mode. OpenJarvis AI is not available.\n\n"
                   "To enable AI features, please:\n"
                   "1. Install OpenJarvis: pip install openjarvis\n"
                   "2. Configure your AI provider (Ollama, OpenAI, etc.)\n\n"
                   "You can still use the DAW's built-in features for music production.")
        self.response_ready.emit(session_id, response)
        return response
        
    def ask_async(self, *args, **kwargs):
        """Async version just calls sync version"""
        response = self.ask(*args, **kwargs)
        
    def initialize(self, *args, **kwargs) -> bool:
        return True
        
    def close(self):
        pass
