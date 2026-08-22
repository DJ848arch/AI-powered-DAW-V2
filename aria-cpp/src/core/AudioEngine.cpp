#include "AudioEngine.h"

// Tracktion Engine headers — pulled in only in this translation unit
#include <tracktion_engine/tracktion_engine.h>

namespace te = tracktion::engine;

namespace aria {

AudioEngine::AudioEngine()  = default;
AudioEngine::~AudioEngine() { shutdown(); }

bool AudioEngine::initialise()
{
    if (running_) return true;

    // ── Tracktion Engine ──────────────────────────────────────────────────────
    te::Engine::InitialisationInfo info;
    info.applicationName = "ARIA";
    engine_ = std::make_unique<te::Engine>(info);

    // ── Audio device ──────────────────────────────────────────────────────────
    // Default audio device (WASAPI on Windows, CoreAudio on macOS)
    auto err = deviceManager_.initialiseWithDefaultDevices(0, 2);
    if (err.isNotEmpty()) {
        juce::Logger::writeToLog("[AudioEngine] Device init error: " + err);
        // Continue anyway — the user can reconfigure in settings
    }

    // ── Empty Edit ────────────────────────────────────────────────────────────
    rebuildEditFromDoc(*songDoc_.load());

    running_ = true;
    return true;
}

void AudioEngine::shutdown()
{
    if (!running_) return;
    stop();
    edit_.reset();
    engine_.reset();
    deviceManager_.closeAudioDevice();
    running_ = false;
}

bool AudioEngine::isRunning() const noexcept { return running_; }

// ── Song document swap ────────────────────────────────────────────────────────

void AudioEngine::atomicSwapDoc(std::shared_ptr<SongDocument> newDoc)
{
    songDoc_.store(newDoc);

    // Rebuild the Tracktion Edit on the message thread (safe for UI updates)
    juce::MessageManager::callAsync([this] {
        if (auto doc = songDoc_.load())
            rebuildEditFromDoc(*doc);
    });
}

std::shared_ptr<const SongDocument> AudioEngine::currentDoc() const
{
    return songDoc_.load();
}

// ── Transport ─────────────────────────────────────────────────────────────────

void AudioEngine::play()
{
    if (edit_)
        edit_->getTransport().play(false);
}

void AudioEngine::pause()
{
    if (edit_)
        edit_->getTransport().stop(false, false);
}

void AudioEngine::stop()
{
    if (edit_) {
        edit_->getTransport().stop(false, false);
        edit_->getTransport().setCurrentPosition(0.0);
    }
}

void AudioEngine::setLoopRegion(bool enabled, int startBar, int endBar)
{
    if (!edit_) return;
    auto& transport = edit_->getTransport();
    transport.looping = enabled;
    if (enabled) {
        float beatsPerBar = static_cast<float>(
            songDoc_.load()->metadata().timeSignature.numerator);
        transport.setLoopIn(te::TimePosition::fromBeats(startBar * beatsPerBar));
        transport.setLoopOut(te::TimePosition::fromBeats(endBar   * beatsPerBar));
    }
}

bool AudioEngine::isPlaying() const noexcept
{
    if (!edit_) return false;
    return edit_->getTransport().isPlaying();
}

double AudioEngine::currentPositionBeats() const noexcept
{
    if (!edit_) return 0.0;
    // Tracktion reports position in seconds; convert to beats
    double posSeconds = edit_->getTransport().getCurrentPosition().inSeconds();
    double bpm        = static_cast<double>(songDoc_.load()->metadata().bpm);
    return posSeconds * (bpm / 60.0);
}

// ── MIDI ──────────────────────────────────────────────────────────────────────

void AudioEngine::sendNoteOn(int midiChannel, int pitch, int velocity)
{
    if (!edit_) return;
    // TODO: route to the correct track's instrument via Tracktion's MIDI injector
    juce::ignoreUnused(midiChannel, pitch, velocity);
}

void AudioEngine::sendNoteOff(int midiChannel, int pitch)
{
    if (!edit_) return;
    juce::ignoreUnused(midiChannel, pitch);
}

// ── Device manager ────────────────────────────────────────────────────────────

juce::AudioDeviceManager& AudioEngine::deviceManager() noexcept
{
    return deviceManager_;
}

te::Engine* AudioEngine::tracktionEngine() noexcept { return engine_.get(); }
te::Edit*   AudioEngine::currentEdit()     noexcept { return edit_.get();   }

// ── Edit rebuild ──────────────────────────────────────────────────────────────

void AudioEngine::rebuildEditFromDoc(const SongDocument& doc)
{
    // TODO (vertical slice): map SongDocument tracks to Tracktion Edit tracks.
    // For now, create a blank Edit at the correct tempo.
    juce::ignoreUnused(doc);

    if (!engine_) return;

    // Create a new in-memory Edit
    auto newEdit = te::createEmptyEdit(*engine_);
    if (!newEdit) return;

    // Set tempo
    newEdit->tempoSequence.addTempo({}, doc.metadata().bpm);

    edit_ = std::move(newEdit);

    // Wire edit to audio device
    engine_->getDeviceManager().setDefaultDeviceNames({}, {});
}

} // namespace aria
