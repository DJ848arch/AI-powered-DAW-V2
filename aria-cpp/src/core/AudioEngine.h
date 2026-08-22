#pragma once

#include "SongDocument.h"
#include <juce_audio_devices/juce_audio_devices.h>
#include <juce_audio_processors/juce_audio_processors.h>
#include <memory>

// Forward declare Tracktion Engine types to avoid pulling in the full header
// everywhere AudioEngine.h is included.
namespace tracktion { namespace engine { class Engine; class Edit; } }

namespace aria {

// ─────────────────────────────────────────────────────────────────────────────
//  AudioEngine
//
//  Wraps Tracktion Engine. Owns the te::Edit (the "project" in Tracktion terms).
//  Thread-safe: all public methods may be called from the message thread.
//  Audio processing happens on the audio thread automatically via Tracktion.
// ─────────────────────────────────────────────────────────────────────────────

class AudioEngine {
public:
    AudioEngine();
    ~AudioEngine();

    // Prevent copy
    AudioEngine(const AudioEngine&) = delete;
    AudioEngine& operator=(const AudioEngine&) = delete;

    // ── Lifecycle ────────────────────────────────────────────────────────────

    /** Initialise audio device and Tracktion Engine. Call once at startup. */
    bool initialise();

    /** Shutdown audio. Call before app exit. */
    void shutdown();

    /** Returns true if the engine is running. */
    bool isRunning() const noexcept;

    // ── Song document swap ────────────────────────────────────────────────────
    /**
     * Replace the current song doc atomically.
     * Rebuilds the Tracktion Edit from the new doc on the message thread.
     * Safe to call from the agent thread — posts to message thread internally.
     */
    void atomicSwapDoc(std::shared_ptr<SongDocument> newDoc);

    /** Read the current doc (any thread). */
    std::shared_ptr<const SongDocument> currentDoc() const;

    // ── Transport ─────────────────────────────────────────────────────────────

    void play();
    void pause();
    void stop();
    void setLoopRegion(bool enabled, int startBar, int endBar);
    bool isPlaying() const noexcept;

    /** Current playback position in beats. */
    double currentPositionBeats() const noexcept;

    // ── MIDI / instrument ────────────────────────────────────────────────────

    /** Route a real-time note-on to a MIDI channel (from MIDI keyboard input). */
    void sendNoteOn(int midiChannel, int pitch, int velocity);
    void sendNoteOff(int midiChannel, int pitch);

    // ── Audio device ─────────────────────────────────────────────────────────

    juce::AudioDeviceManager& deviceManager() noexcept;

    // ── Tracktion Engine (for advanced usage / testing) ───────────────────────
    tracktion::engine::Engine* tracktionEngine() noexcept;
    tracktion::engine::Edit*   currentEdit()     noexcept;

private:
    void rebuildEditFromDoc(const SongDocument& doc);

    AtomicSongDoc                                songDoc_;
    std::unique_ptr<tracktion::engine::Engine>   engine_;
    std::unique_ptr<tracktion::engine::Edit>     edit_;
    juce::AudioDeviceManager                     deviceManager_;
    bool                                         running_ = false;
};

} // namespace aria
