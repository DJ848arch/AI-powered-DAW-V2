# AI-Integrated DAW

A Digital Audio Workstation (DAW) with AI-powered music generation capabilities. Built with PyQt6 and integrated with ElevenLabs API for intelligent music composition assistance.

![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Features

- **Multi-Track Timeline Editor**: Visual timeline with zoom, scroll, and selection
- **Waveform Visualization**: Real-time audio waveform rendering using QPainter
- **Audio Playback Engine**: Full playback controls with play/pause/stop/record
- **Track Controls**: Volume, pan, mute, solo for each track
- **Audio Editing**: Cut, copy, paste, trim operations on audio clips
- **AI Agent Chat**: Interactive chat interface for composition assistance
- **ElevenLabs Integration**: AI-powered music generation via API
- **Project Management**: Save/load projects with JSON serialization
- **Audio Export**: Export to WAV, MP3, FLAC formats
- **Transport Controls**: BPM, time signature, metronome
- **Effects Rack**: Basic effects UI (EQ, compression, reverb, delay)

## Screenshots

*Screenshots will be added in future releases*

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Quick Install

```bash
# Clone the repository
git clone <repository-url>
cd ai-integrated-daw

# Install dependencies
pip install -r requirements.txt

# Run the application
python src/main.py
```

### Manual Setup

1. **Create a virtual environment** (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. **Install dependencies**:
```bash
pip install PyQt6>=6.4.0
pip install pydub>=0.25.1
pip install librosa>=0.10.0
pip install soundfile>=0.12.1
pip install numpy>=1.24.0
pip install requests>=2.28.0
pip install python-dotenv>=1.0.0
```

3. **Configure ElevenLabs API** (optional):
```bash
# Set your API key as environment variable
export ELEVENLABS_API_KEY="your-api-key-here"

# Or create a .env file
echo "ELEVENLABS_API_KEY=your-api-key-here" > .env
```

## Usage

### Starting the Application

```bash
python src/main.py
```

### Basic Workflow

1. **Create a New Project**: File → New Project (Ctrl+N)
2. **Add Tracks**: Track → Add Track (Ctrl+T)
3. **Import Audio**: Right-click on timeline → Import Audio
4. **Edit Clips**: Select clips and use cut/copy/paste/trim operations
5. **Adjust Mix**: Use track panel to set volume, pan, mute, solo
6. **Generate AI Music**: AI Agent → Generate Music (Ctrl+G)
7. **Export**: File → Export Audio (Ctrl+E)

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+N | New Project |
| Ctrl+O | Open Project |
| Ctrl+S | Save Project |
| Ctrl+E | Export Audio |
| Space | Play/Pause |
| Ctrl+T | Add Track |
| Ctrl+Shift+T | Remove Track |
| Ctrl+G | Generate Music |
| Ctrl+Shift+C | Open AI Chat |
| Ctrl++ | Zoom In |
| Ctrl+- | Zoom Out |
| Ctrl+0 | Zoom to Fit |

### AI Agent Features

The AI Agent can help you with:
- **Melody Generation**: "Generate a melody in C major"
- **Chord Progressions**: "Suggest chords for a pop song"
- **Drum Patterns**: "Create a house drum pattern"
- **Bass Lines**: "Add a bass line to my track"
- **Arrangement**: "Help me structure this song"

## Project Structure

```
ai-integrated-daw/
├── src/
│   ├── main.py                 # Application entry point
│   ├── main_window.py          # Main window with menus/toolbars
│   ├── timeline.py             # Multi-track timeline widget
│   ├── track_panel.py          # Track controls (vol/pan/mute/solo)
│   ├── audio_engine.py         # Audio playback engine
│   ├── clip.py                 # Audio clip operations
│   ├── transport_controls.py   # BPM, metronome, transport
│   ├── chat_widget.py          # AI chat interface
│   ├── agent_manager.py        # AI agent management
│   ├── elevenlabs_client.py    # ElevenLabs API client
│   ├── project.py              # Project save/load
│   ├── effects_rack.py         # Effects UI
│   └── export_dialog.py        # Export dialog
├── assets/                     # Audio assets and resources
├── projects/                   # Saved projects
├── exports/                    # Exported audio files
├── requirements.txt            # Python dependencies
├── setup.py                    # Package setup
└── README.md                   # This file
```

## Configuration

### ElevenLabs API Setup

To use AI music generation features:

1. Sign up at [ElevenLabs](https://elevenlabs.io)
2. Get your API key from the dashboard
3. Set the API key:
   - Environment variable: `ELEVENLABS_API_KEY`
   - Or create `~/.aria/elevenlabs_config.json`:
     ```json
     {
       "api_key": "your-api-key-here",
       "default_voice_id": null,
       "default_model": "eleven_monolingual_v1"
     }
     ```

### Audio Settings

Default audio settings:
- Sample Rate: 44100 Hz
- Bit Depth: 16-bit
- Channels: Stereo

These can be changed in the project settings.

## Development

### Running Tests

```bash
# Run all tests
python -m pytest tests/

# Run specific test
python -m pytest tests/test_audio_engine.py
```

### Building from Source

```bash
# Install build dependencies
pip install pyinstaller

# Build executable
pyinstaller --onefile --windowed src/main.py
```

## Troubleshooting

### Common Issues

**Q: Audio playback doesn't work**
- Ensure your system audio is properly configured
- Check that sounddevice is installed: `pip install sounddevice`
- Try selecting a different audio device

**Q: ElevenLabs integration not working**
- Verify your API key is set correctly
- Check your internet connection
- Ensure you have available quota on your ElevenLabs account

**Q: Import errors**
- Make sure all dependencies are installed: `pip install -r requirements.txt`
- Verify Python version is 3.8 or higher

**Q: Waveform not displaying**
- Ensure audio file is valid and supported (WAV, MP3, FLAC, OGG)
- Check that librosa and soundfile are installed

### Platform-Specific Notes

**Windows:**
- May require Visual C++ Redistributable
- Use `python` instead of `python3`

**macOS:**
- May require Xcode command line tools
- Use `python3` instead of `python`

**Linux:**
- May require additional audio libraries: `sudo apt-get install libportaudio2`
- For MP3 support: `sudo apt-get install ffmpeg`

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Built with [PyQt6](https://www.riverbankcomputing.com/software/pyqt/)
- Audio processing with [librosa](https://librosa.org/) and [soundfile](https://python-soundfile.readthedocs.io/)
- AI integration with [ElevenLabs](https://elevenlabs.io)
- Icons and UI inspired by professional DAWs

## Roadmap

- [ ] MIDI support and virtual instruments
- [ ] VST plugin support
- [ ] Advanced audio effects (real-time processing)
- [ ] Collaboration features
- [ ] Cloud project storage
- [ ] Mobile companion app
- [ ] Advanced AI composition features

## Support

For support, please open an issue on GitHub or contact the development team.

---

**Version:** 1.0.0  
**Last Updated:** 2024
