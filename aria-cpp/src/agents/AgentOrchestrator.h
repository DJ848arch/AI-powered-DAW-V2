#pragma once

#include "core/SongDocument.h"
#include "llm/LLMRuntime.h"
#include <juce_core/juce_core.h>
#include <functional>
#include <memory>
#include <string>

namespace aria {

// ─────────────────────────────────────────────────────────────────────────────
//  Generation status — emitted to the UI via callback
// ─────────────────────────────────────────────────────────────────────────────

struct GenerationStatus {
    enum class Stage {
        ChatProcessing,
        ProducerPlanning,
        ConductorBriefing,
        TrackGenerating,
        Building,
        Done,
        Error
    };

    Stage        stage     = Stage::ChatProcessing;
    std::string  message;          // human-readable status message
    std::string  currentInstrument; // set during TrackGenerating stage
    int          tracksComplete  = 0;
    int          tracksTotal     = 0;
    float        progressPercent = 0.0f;
};

// ─────────────────────────────────────────────────────────────────────────────
//  AgentOrchestrator
//
//  Runs the Chat → Producer → Conductor → TrackAgents pipeline.
//  All heavy work happens on an internal background thread.
//  Results are posted to the message thread via callbacks.
// ─────────────────────────────────────────────────────────────────────────────

class AgentOrchestrator {
public:
    // Callbacks (called on the message thread)
    using StatusCallback = std::function<void(GenerationStatus)>;
    using TokenCallback  = std::function<void(std::string_view token)>;  // streaming
    using DocCallback    = std::function<void(std::shared_ptr<SongDocument>)>;

    explicit AgentOrchestrator(LLMRuntime& llm);
    ~AgentOrchestrator();

    // Non-copyable
    AgentOrchestrator(const AgentOrchestrator&) = delete;
    AgentOrchestrator& operator=(const AgentOrchestrator&) = delete;

    // ── Pipeline ─────────────────────────────────────────────────────────────

    /**
     * Start a full generation pipeline from a user message.
     * Non-blocking — starts the agent thread and returns immediately.
     * Calls statusCallback as each stage progresses.
     * Calls docCallback once with the completed SongDocument.
     */
    void generateFromUserMessage(
        const std::string&   userMessage,
        const SongDocument&  currentDoc,
        StatusCallback       statusCallback,
        TokenCallback        chatTokenCallback,
        DocCallback          docCallback
    );

    /** Cancel any running generation. */
    void cancel();

    /** True if the pipeline is currently running. */
    bool isRunning() const noexcept;

    // ── Feedback ──────────────────────────────────────────────────────────────

    /**
     * Record user feedback about the last generation.
     * Called after the user answers "What did you think?" and explains.
     * Runs asynchronously — does not block the UI.
     */
    void recordFeedback(const std::string& ratingText,
                        const std::string& explanation);

private:
    void runPipeline(
        std::string          userMessage,
        SongDocument         currentDoc,
        StatusCallback       statusCallback,
        TokenCallback        chatTokenCallback,
        DocCallback          docCallback
    );

    LLMRuntime&            llm_;
    std::unique_ptr<juce::Thread> thread_;
    std::atomic<bool>      running_    { false };
    std::atomic<bool>      cancelled_  { false };

    // Last generation context (for feedback)
    struct LastGen {
        std::string vibe, genre, key;
        float       bpm  = 120.f;
        int         bars = 8;
        std::vector<std::string> instruments;
    } lastGen_;
};

} // namespace aria
