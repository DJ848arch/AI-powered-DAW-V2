# ARIA-CPP Vertical Slice — First Milestone

**Demo goal:**
> User types "make me an 80 BPM lo-fi hip hop beat in A minor, 4 bars"
> → ARIA generates drums, bass, piano, pad
> → Notes appear in the arrangement
> → Transport plays back the beat using a soundfont

---

## What "Done" Looks Like for This Milestone

1. App opens, window is visible with IRA chat panel, piano roll stub, mixer stub
2. User types the prompt above and presses Enter
3. IRA responds "Let me put that together for you..."
4. Status bar updates: "Planning arrangement" → "Writing drums..." → "Writing bass..." → "Done!"
5. Four tracks appear in the arrangement view (or just the piano roll for milestone 1)
6. User presses Space — playback starts via Tracktion Engine
7. Notes are audible via the default audio device (using a built-in soundfont or FluidSynth)
8. Playhead animates across the piano roll at the correct tempo
9. User types "that was ok but the bass was too busy" — IRA says "Got it, I'll remember that"
10. `~/.aria-cpp/agent_memory.json` file exists and contains the feedback entry

---

## File Checklist — Everything Needed to Compile and Run

### CMake / Build
- [x] `CMakeLists.txt`

### Entry Point
- [x] `src/main.cpp`

### Core
- [x] `src/core/SongDocument.h` / `.cpp`
- [x] `src/core/AudioEngine.h` / `.cpp`
- [x] `src/core/InstrumentRegistry.h` / `.cpp`

### LLM Runtime
- [x] `src/llm/LLMRuntime.h` / `.cpp`

### Agents
- [x] `src/agents/AgentOrchestrator.h` / `.cpp`
- [x] `src/agents/ChatAgent.h` / `.cpp`
- [x] `src/agents/ProducerAgent.h` / `.cpp`
- [x] `src/agents/ConductorAgent.h` / `.cpp`
- [x] `src/agents/TrackAgent.h` / `.cpp`

### UI
- [x] `src/ui/MainWindow.h` / `.cpp`
- [x] `src/ui/IRAPanel.h` / `.cpp`
- [x] `src/ui/PianoRollWindow.h` / `.cpp`  ← stub, paints notes only
- [x] `src/ui/MixerPanel.h` / `.cpp`       ← stub, no audio routing yet

### Plugins
- [x] `src/plugins/PluginHost.h` / `.cpp`
- [x] `src/plugins/PluginRegistry.h` / `.cpp`
- [x] `src/plugins/PluginScannerMain.cpp`

### Resources
- [x] `resources/agents/CHAT.md`
- [x] `resources/agents/PRODUCER.md`
- [x] `resources/agents/CONDUCTOR.md`
- [x] `resources/agents/TRACK.md`
- [x] `resources/schemas/song_schema.json`
- [ ] `resources/models/qwen2.5-7b-instruct-q4_k_m.gguf` ← **you must download this**

### Tests
- [x] `tests/SongDocumentTests.cpp`
- [x] `tests/LLMRuntimeTests.cpp`
- [x] `tests/AgentPipelineTests.cpp`

---

## Files NOT in Milestone 1 (deferred to later milestones)

| File / Feature                         | Milestone |
|----------------------------------------|-----------|
| Arrangement view (clip drag/resize)    | 2         |
| Plugin hosting (VST3/AU/CLAP inserts)  | 2         |
| Agent memory JSON save/load            | 2         |
| MIDI keyboard recording                | 2         |
| WAV export                             | 3         |
| Mixer FX chain (EQ, reverb, comp)      | 3         |
| Multi-track audio recording            | 3         |
| Undo/redo full implementation          | 3         |
| Soundfont browser                      | 3         |
| Piano roll note editing (draw/erase)   | 2         |

---

## Development Order for Milestone 1

Work through these tasks in sequence. Each builds on the previous.

### Step 1 — Get it to compile
```
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Debug
cmake --build . --target aria_cpp -j8
```
Expected: 0 link errors, app launches and shows a black window.

Known issues to fix first:
- `AudioEngine.cpp` uses `te::createEmptyEdit()` — check exact Tracktion 9 API name
- `AgentOrchestrator.cpp` uses `juce::GenericThread` — may need `juce::Thread` subclass instead
- `IRAPanel.cpp` holds a ref to `SongDocument::empty()` — wire in AudioEngine reference

### Step 2 — IRA chat responds
Goal: user types a message, IRA responds with generated text (streaming tokens).
- Model must be in `resources/models/`
- ChatAgent → LLMRuntime::inferStream() → IRAPanel::streamToken()
- No generation yet — just the chat reply appearing token by token

### Step 3 — Full pipeline runs
Goal: "make me a lo-fi beat" produces 4 Track objects in the SongDocument.
- ChatAgent → ProducerAgent → ConductorAgent → TrackAgent × 4
- Status updates appear in IRA panel: "Writing drums...", etc.
- After completion: IRA asks "What did you think?"

### Step 4 — Notes visible in Piano Roll
Goal: notes from the generated drums track appear in PianoRollWindow.
- MainWindow::onNewDocumentGenerated() → passes first track's clip to pianoRoll_->setClip()
- Coloured rectangles visible in the grid

### Step 5 — Playback works
Goal: Space bar plays the beat, you hear audio.
- AudioEngine::play() → Tracktion transport starts
- AudioEngine::rebuildEditFromDoc() must actually build the Tracktion Edit with MIDI clips
  (this is the most complex step — see Tracktion Engine MidiClip/MidiList API)
- Playhead animates in PianoRollWindow

### Step 6 — Feedback loop
Goal: user types "the bass was too busy", it's saved to agent_memory.json.
- IRAPanel feedback state machine
- AgentOrchestrator::recordFeedback() writes to `~/.aria-cpp/agent_memory.json`

---

## Key API References

### Tracktion Engine — creating MIDI content
```cpp
// Create a MIDI track
auto* audioTrack = te::getAudioTracks(edit)[0];

// Create a MIDI clip at bar 0, length = 4 beats
auto* midiClip = dynamic_cast<te::MidiClip*>(
    audioTrack->insertMidiClip("Piano", { te::TimePosition::fromBeats(0),
                                          te::TimePosition::fromBeats(4) },
                               nullptr));

// Add notes to the clip
auto& midiList = midiClip->getSequence();
midiList.addNote(60, te::BeatPosition::fromBeats(0.0), te::BeatDuration::fromBeats(1.0), 80, 0, nullptr);
```

### Tracktion Engine — assigning an instrument plugin
```cpp
// Load a SoundFont player plugin (built into Tracktion Engine)
auto& pluginList = audioTrack->pluginList;
auto* sampler = dynamic_cast<te::SamplerPlugin*>(
    pluginList.insertPlugin(te::SamplerPlugin::create(*audioTrack), 0, nullptr));
sampler->addSound("/path/to/soundfont.sf2", "GM Piano", 0, 127, 100);
```

### llama.cpp — Qwen 2.5 Instruct chat template
```
<|im_start|>system
{system_prompt}
<|im_end|>
<|im_start|>user
{user_message}
<|im_end|>
<|im_start|>assistant
```
(This is already implemented in `LLMRuntime::Impl::buildPrompt()`)

---

## Where to Get the Model

**Qwen 2.5 7B Instruct Q4_K_M** (~4.5 GB):
```
https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf
```

Place it at: `aria-cpp/resources/models/qwen2.5-7b-instruct-q4_k_m.gguf`

Alternatively, any 7B instruct model using Qwen chat format will work.
Smaller option for testing: Qwen 2.5 3B Q4_K_M (~2 GB).

---

## Build Requirements

| Platform | Requirement                                              |
|----------|----------------------------------------------------------|
| Windows  | Visual Studio 2022, CMake 3.24+, Git                     |
| macOS    | Xcode 15+, CMake 3.24+, Git                              |
| Both     | ~8 GB RAM minimum (4.5 GB for model + app overhead)      |
| Both     | ~6 GB disk (model + build artifacts)                     |

GPU acceleration (optional):
- Windows CUDA: set `LLAMA_CUDA=ON` in CMake, requires NVIDIA GPU + CUDA toolkit
- macOS Metal: automatic if llama.cpp detects Metal (Apple Silicon)
