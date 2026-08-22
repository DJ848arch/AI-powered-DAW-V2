# ARIA-CPP Architecture

> **Fully offline, cross-platform (macOS + Windows) AI-assisted DAW**
> Built on JUCE 8 + Tracktion Engine 9 · llama.cpp embedded in-process
> Agent LLM: Qwen 2.5 7B Instruct Q4_K_M (~4.5 GB)

---

## 1. High-Level Component Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                          ARIA-CPP Process                            │
│                                                                      │
│  ┌─────────────┐    ┌──────────────────┐    ┌────────────────────┐  │
│  │   UI Layer  │    │  Agent Pipeline  │    │   Audio Engine     │  │
│  │  (JUCE/GUI) │◄──►│ AgentOrchestrator│    │  (Tracktion Eng.)  │  │
│  │             │    │  ChatAgent       │    │  AudioEngine       │  │
│  │ MainWindow  │    │  ProducerAgent   │    │  PluginHost        │  │
│  │ PianoRoll   │    │  ConductorAgent  │    │  AudioDeviceMgr    │  │
│  │ Mixer       │    │  TrackAgents[N]  │    │                    │  │
│  │ IRAPanel    │    └────────┬─────────┘    └────────┬───────────┘  │
│  └──────┬──────┘             │                       │              │
│         │              ┌─────▼──────┐                │              │
│         │              │ LLMRuntime │                 │              │
│         │              │ (llama.cpp)│                 │              │
│         │              └────────────┘                 │              │
│         │                                             │              │
│         └──────────── SongDocument ──────────────────┘              │
│                     (immutable value, atomic swap)                   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Threading Model

```
Thread          │ Owns / Touches                         │ Rules
────────────────┼─────────────────────────────────────────┼──────────────────────────────
Message Thread  │ All JUCE UI widgets, MainWindow,        │ Never block. No llama.cpp.
(JUCE GUI)      │ IRAPanel, PianoRoll, Mixer              │ All Qt-style connections
                │                                         │ via MessageManagerLock or
                │                                         │ callAsync().
────────────────┼─────────────────────────────────────────┼──────────────────────────────
Audio Thread    │ Tracktion Engine process callback,       │ REAL-TIME. Zero allocations,
(RT)            │ AudioEngine::processBlock()              │ zero locks, no LLM calls.
                │ Reads SongDocument via atomic load()     │ Read atomic<shared_ptr> only.
────────────────┼─────────────────────────────────────────┼──────────────────────────────
Agent Thread    │ AgentOrchestrator, all Agent subclasses,│ Long-running. Owns LLMRuntime.
(background)    │ LLMRuntime::infer() / inferStream()     │ Writes new SongDocument then
                │                                         │ atomically swaps the pointer.
                │                                         │ Posts result to message thread
                │                                         │ via callAsync() for UI refresh.
────────────────┼─────────────────────────────────────────┼──────────────────────────────
Disk I/O Thread │ Project load/save, soundfont scanning   │ juce::ThreadPoolJob.
(pool)          │ Plugin scanning                         │ Never touches audio graph.
```

### Song Document Swap Protocol

```
Agent Thread                          Audio Thread
────────────                          ────────────
Build next_doc (new SongDocument)
Call AudioEngine::atomicSwapDoc(next_doc)
  → lock-free: song_.store(next_doc, memory_order_release)
                                      song_.load(memory_order_acquire)  // reads new doc
```

The `SongDocument` is an **immutable value type** (deep-copied before mutation). The audio thread never mutates it — it only reads via `std::atomic<std::shared_ptr<SongDocument>>`.

---

## 3. Why Tracktion Engine (not raw JUCE)

| Concern                     | Raw JUCE                            | Tracktion Engine                        |
|-----------------------------|-------------------------------------|-----------------------------------------|
| Timeline / transport        | Build from scratch (~3 months)      | **Included.** Edit::getTransport()      |
| MIDI clip / note sequencing | Build from scratch                  | **MidiClip, MidiList built-in**         |
| Plugin hosting (VST3/AU)    | PluginManager (manual graph)        | **Rack + Insert pattern, auto graph**   |
| Audio graph routing         | AudioProcessorGraph (manual)        | **Edit graph managed automatically**    |
| Undo/redo                   | Build UndoManager plumbing          | **UndoManager baked in at Edit level**  |
| Project file format         | Build from scratch                  | **te::Edit::save/load via ValueTree**   |
| License                     | GPL/Commercial (JUCE)               | GPL/Commercial (same as JUCE)           |

**Decision: Tracktion Engine.** Saves ~12 months of DAW plumbing. ARIA-CPP wraps it behind `AudioEngine` and `SongDocument` so it can be swapped later.

---

## 4. Agent Pipeline Data Flow

```
User types message
      │
      ▼
┌─────────────┐   system prompt + history
│  ChatAgent  │──────────────────────────► LLMRuntime::infer()
│             │◄── intent JSON ────────────────────────────────
└──────┬──────┘
       │ intent: {type:"generate", vibe, genre, bpm, key, bars}
       ▼
┌──────────────┐   plan context
│ProducerAgent │──► LLMRuntime::infer()
│              │◄── arrangement JSON {tracks:[{instrument,role,style},...]}
└──────┬───────┘
       │
       ▼
┌───────────────┐   arrangement + brief
│ConductorAgent │──► LLMRuntime::infer()
│               │◄── per-track briefs JSON {briefs:[{instrument,section,...}]}
└──────┬────────┘
       │  ┌──────────────────────────────────────────────────────┐
       │  │  Sequential loop (drums → bass → piano → ... → lead) │
       ▼  ▼                                                      │
┌──────────────┐  brief + completed_tracks_so_far               │
│  TrackAgent  │──► LLMRuntime::infer()                         │
│  (per inst.) │◄── notes JSON {notes:[{pitch,start,dur,vel}]}  │
└──────┬───────┘                                                 │
       └─────────────────────────────────────────────────────────┘
       │  all tracks complete
       ▼
AgentOrchestrator builds new SongDocument
       │
       ▼
AudioEngine::atomicSwapDoc(newDoc)   ← audio thread reads immediately
       │
       ▼
callAsync → MainWindow::refreshFromDoc()  ← UI redraws
```

---

## 5. Plugin Hosting Architecture

```
PluginHost
  ├── scanPlugins()          — runs in disk thread, builds PluginRegistry
  ├── loadPlugin(id) → PluginInstance*
  ├── insertOnTrack(trackId, slot, plugin)
  └── PluginRegistry         — persisted to ~/.aria-cpp/plugin_cache.json

AudioEngine (wraps te::Edit)
  └── te::Edit
       └── te::AudioTrack[N]
            └── te::PluginList
                 ├── te::VolumeAndPanPlugin (always first)
                 └── User VST3/AU/CLAP inserts
```

Plugin format support:
- **VST3** — via JUCE PluginManager (all platforms)
- **AU** — via JUCE PluginManager (macOS only)
- **CLAP** — via `clap-juce-extensions` (FetchContent, see CMake)

---

## 6. LLM Runtime Design

```cpp
// pimpl hides all llama.cpp headers from the rest of the codebase
class LLMRuntime {
public:
    struct Params {
        std::filesystem::path modelPath;
        int contextSize   = 4096;
        int threads       = 8;
        float temperature = 0.7f;
        int maxTokens     = 1024;
    };

    explicit LLMRuntime(Params p);
    ~LLMRuntime();

    // Synchronous — blocks agent thread until complete
    std::string infer(std::string_view systemPrompt,
                      std::string_view userPrompt);

    // Streaming — calls cb(token) on agent thread for each new token
    void inferStream(std::string_view systemPrompt,
                     std::string_view userPrompt,
                     std::function<void(std::string_view token)> cb);

    // JSON-constrained output via GBNF grammar
    std::string inferJSON(std::string_view systemPrompt,
                          std::string_view userPrompt,
                          std::string_view gbnfGrammar);

    bool isLoaded() const noexcept;
    std::string modelName() const;

private:
    struct Impl;                // defined only in LLMRuntime.cpp
    std::unique_ptr<Impl> d_;   // pimpl — llama.cpp types never escape
};
```

**GBNF grammar** is used for all structured JSON outputs (notes, arrangements, briefs). This guarantees the LLM output parses without retry loops.

---

## 7. SongDocument Value Type

```
SongDocument
├── metadata: {title, bpm, key, timeSignature, bars}
├── tracks[]:
│    ├── id: UUID string
│    ├── name: string
│    ├── instrument: string   (maps to GM program via InstrumentRegistry)
│    ├── midiChannel: int     (0-15)
│    ├── volume: float        (0.0-1.0)
│    ├── pan: float           (-1.0 to 1.0)
│    ├── muted: bool
│    ├── solo: bool
│    ├── clips[]:
│    │    ├── id: UUID
│    │    ├── startBar: int
│    │    └── notes[]: {pitch, startBeat, durationBeats, velocity}
│    └── pluginChain[]: {pluginId, state: base64}
└── agentMemory: {likedAspects[], dislikedAspects[], perInstrument{}}
```

Serialises to/from JSON (nlohmann/json, header-only FetchContent) and to/from `juce::ValueTree` for Tracktion Engine integration.

---

## 8. Directory Layout

```
aria-cpp/
├── CMakeLists.txt
├── ARCHITECTURE.md
├── src/
│   ├── main.cpp
│   ├── core/
│   │   ├── SongDocument.h / .cpp
│   │   ├── AudioEngine.h / .cpp
│   │   └── InstrumentRegistry.h / .cpp
│   ├── agents/
│   │   ├── AgentOrchestrator.h / .cpp
│   │   ├── ChatAgent.h / .cpp
│   │   ├── ProducerAgent.h / .cpp
│   │   ├── ConductorAgent.h / .cpp
│   │   └── TrackAgent.h / .cpp
│   ├── llm/
│   │   ├── LLMRuntime.h
│   │   └── LLMRuntime.cpp
│   ├── plugins/
│   │   ├── PluginHost.h / .cpp
│   │   └── PluginRegistry.h / .cpp
│   └── ui/
│       ├── MainWindow.h / .cpp
│       ├── IRAPanel.h / .cpp
│       ├── PianoRollWindow.h / .cpp
│       └── MixerPanel.h / .cpp
├── resources/
│   ├── models/          ← place Qwen 2.5 7B Q4_K_M .gguf here
│   ├── agents/
│   │   ├── CHAT.md
│   │   ├── PRODUCER.md
│   │   ├── CONDUCTOR.md
│   │   └── TRACK.md
│   └── schemas/
│       └── song_schema.json
└── tests/
    ├── SongDocumentTests.cpp
    ├── LLMRuntimeTests.cpp
    └── AgentPipelineTests.cpp
```

---

## 9. Build Targets

| Target               | Type        | Description                                      |
|----------------------|-------------|--------------------------------------------------|
| `aria_cpp`           | Executable  | Main DAW application                            |
| `aria_tests`         | Executable  | CTest unit + integration tests                   |
| `aria_plugin_scan`   | Executable  | Headless plugin scanner (child process)          |

---

## 10. Key Third-Party Dependencies

| Library               | Version  | How Fetched              | License     |
|-----------------------|----------|--------------------------|-------------|
| JUCE                  | 8.x      | FetchContent (GitHub)    | GPL/Comm.   |
| Tracktion Engine      | 9.x      | FetchContent (GitHub)    | GPL/Comm.   |
| llama.cpp             | latest   | FetchContent (GitHub)    | MIT         |
| nlohmann/json         | 3.11.x   | FetchContent (GitHub)    | MIT         |
| clap-juce-extensions  | latest   | FetchContent (GitHub)    | MIT         |
| Catch2                | 3.x      | FetchContent (tests only)| BSL-1.0     |
