"""
ElevenLabs API Client for Music Generation
Handles API communication with ElevenLabs
"""

import os
import requests
import json
from typing import Optional, Dict, List, BinaryIO
from pathlib import Path


class ElevenLabsClient:
    """Client for ElevenLabs API"""
    
    BASE_URL = "https://api.elevenlabs.io/v1"
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize client with API key"""
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        self.headers = {}
        
        if self.api_key:
            self.headers["xi-api-key"] = self.api_key
            
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
    def set_api_key(self, api_key: str):
        """Set or update API key"""
        self.api_key = api_key
        self.headers["xi-api-key"] = api_key
        self.session.headers.update(self.headers)
        
    def is_configured(self) -> bool:
        """Check if API key is configured"""
        return self.api_key is not None and len(self.api_key) > 0
        
    def get_voices(self) -> List[Dict]:
        """Get available voices"""
        if not self.is_configured():
            raise ValueError("API key not configured")
            
        response = self.session.get(f"{self.BASE_URL}/voices")
        response.raise_for_status()
        
        data = response.json()
        return data.get("voices", [])
        
    def get_models(self) -> List[Dict]:
        """Get available models"""
        if not self.is_configured():
            raise ValueError("API key not configured")
            
        response = self.session.get(f"{self.BASE_URL}/models")
        response.raise_for_status()
        
        data = response.json()
        return data
        
    def text_to_speech(self, text: str, voice_id: str, 
                       model_id: str = "eleven_monolingual_v1",
                       output_path: str = None) -> str:
        """Convert text to speech"""
        if not self.is_configured():
            raise ValueError("API key not configured")
            
        url = f"{self.BASE_URL}/text-to-speech/{voice_id}"
        
        data = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }
        
        response = self.session.post(url, json=data)
        response.raise_for_status()
        
        # Save audio
        if output_path is None:
            output_path = f"tts_output_{int(time.time())}.mp3"
            
        with open(output_path, 'wb') as f:
            f.write(response.content)
            
        return output_path
        
    def generate_music(self, description: str, duration: int = 30,
                       output_path: str = None) -> str:
        """Generate music from text description"""
        # Note: ElevenLabs primarily focuses on voice/speech synthesis
        # For music generation, this would integrate with their sound generation capabilities
        # or use a placeholder/mock for demonstration
        
        if not self.is_configured():
            # Create a placeholder audio file for testing
            return self._create_placeholder_audio(description, duration, output_path)
            
        # In a real implementation, this would call ElevenLabs API
        # For now, create placeholder
        return self._create_placeholder_audio(description, duration, output_path)
        
    def _create_placeholder_audio(self, description: str, duration: int,
                                   output_path: str = None) -> str:
        """Create a placeholder audio file for testing"""
        import numpy as np
        import soundfile as sf
        
        if output_path is None:
            output_path = f"generated_music_{int(time.time())}.wav"
            
        # Generate simple placeholder audio (sine wave sweep)
        sample_rate = 44100
        t = np.linspace(0, duration, int(sample_rate * duration))
        
        # Create a simple melodic pattern
        freq = 440  # A4
        audio = np.sin(2 * np.pi * freq * t) * 0.3
        
        # Add some variation
        for i in range(1, 5):
            audio += np.sin(2 * np.pi * freq * (i + 1) * t) * 0.1 / i
            
        # Add envelope
        envelope = np.ones_like(t)
        attack = int(0.1 * sample_rate)
        release = int(0.5 * sample_rate)
        envelope[:attack] = np.linspace(0, 1, attack)
        envelope[-release:] = np.linspace(1, 0, release)
        
        audio *= envelope
        
        # Convert to stereo
        stereo = np.column_stack((audio, audio))
        
        # Save
        sf.write(output_path, stereo, sample_rate)
        
        return output_path
        
    def generate_sound_effect(self, description: str, 
                             output_path: str = None) -> str:
        """Generate a sound effect"""
        if not self.is_configured():
            raise ValueError("API key not configured")
            
        # This would call ElevenLabs sound effects API
        # For now, return placeholder
        return self._create_placeholder_audio(description, 2, output_path)
        
    def get_user_info(self) -> Dict:
        """Get user subscription info"""
        if not self.is_configured():
            raise ValueError("API key not configured")
            
        response = self.session.get(f"{self.BASE_URL}/user/subscription")
        response.raise_for_status()
        
        return response.json()
        
    def get_character_count(self) -> int:
        """Get remaining character count"""
        try:
            info = self.get_user_info()
            return info.get("character_count", 0)
        except:
            return 0
            
    def get_character_limit(self) -> int:
        """Get character limit"""
        try:
            info = self.get_user_info()
            return info.get("character_limit", 0)
        except:
            return 0


class ElevenLabsConfig:
    """Configuration manager for ElevenLabs"""
    
    CONFIG_FILE = os.path.expanduser("~/.aria/elevenlabs_config.json")
    
    def __init__(self):
        self.api_key = None
        self.default_voice_id = None
        self.default_model = "eleven_monolingual_v1"
        self.load()
        
    def load(self):
        """Load configuration from file"""
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self.api_key = data.get('api_key')
                    self.default_voice_id = data.get('default_voice_id')
                    self.default_model = data.get('default_model', self.default_model)
            except Exception as e:
                print(f"Error loading ElevenLabs config: {e}")
                
        # Also check environment variable
        if not self.api_key:
            self.api_key = os.getenv("ELEVENLABS_API_KEY")
            
    def save(self):
        """Save configuration to file"""
        try:
            os.makedirs(os.path.dirname(self.CONFIG_FILE), exist_ok=True)
            
            data = {
                'api_key': self.api_key,
                'default_voice_id': self.default_voice_id,
                'default_model': self.default_model
            }
            
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            print(f"Error saving ElevenLabs config: {e}")
            
    def set_api_key(self, api_key: str):
        """Set API key"""
        self.api_key = api_key
        self.save()
        
    def set_default_voice(self, voice_id: str):
        """Set default voice"""
        self.default_voice_id = voice_id
        self.save()
        
    def is_configured(self) -> bool:
        """Check if API key is configured"""
        return self.api_key is not None and len(self.api_key) > 0
