#include "AgentOrchestrator.h"
#include "ChatAgent.h"
#include "ProducerAgent.h"
#include "ConductorAgent.h"
#include "TrackAgent.h"

#include <juce_core/juce_core.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace aria {

// Generation order — each instrument sees all previously written tracks
static const std::vector<std::string> kGenerationOrder = {
    "drums", "bass", "piano", "electric_piano", "organ",
    "guitar", "electric_guitar", "strings", "pad", "lead_synth",
    "brass", "woodwind", "choir", "fx"
};

// ─────────────────────────────────────────────────────────────────────────────

AgentOrchestrator::AgentOrchestrator(LLMRuntime& llm)
    : llm_(llm)
{
}

AgentOrchestrator::~AgentOrchestrator()
{
    cancel();
    if (thread_) thread_->waitForThreadToExit(5000);
}

bool AgentOrchestrator::isRunning() const noexcept { return running_.load(); }

void AgentOrchestrator::cancel()
{
    cancelled_.store(true);
    llm_.cancel();
}

// ─────────────────────────────────────────────────────────────────────────────
//  Public entry point (non-blocking)
// ─────────────────────────────────────────────────────────────────────────────

void AgentOrchestrator::generateFromUserMessage(
    const std::string&   userMessage,
    const SongDocument&  currentDoc,
    StatusCallback       statusCallback,
    TokenCallback        chatTokenCallback,
    DocCallback          docCallback)
{
    if (running_.load()) {
        cancel();
        if (thread_) thread_->waitForThreadToExit(3000);
    }

    cancelled_.store(false);
    running_.store(true);

    auto docCopy = currentDoc.clone();

    // Capture all callbacks by value; run pipeline on a background thread
    thread_ = std::make_unique<juce::GenericThread>("aria-agent",
        [this,
         msg    = userMessage,
         doc    = std::move(docCopy),
         scb    = std::move(statusCallback),
         tcb    = std::move(chatTokenCallback),
         dcb    = std::move(docCallback)]() mutable
    {
        runPipeline(std::move(msg), std::move(doc), std::move(scb), std::move(tcb), std::move(dcb));
        running_.store(false);
    });
    thread_->startThread();
}

// ─────────────────────────────────────────────────────────────────────────────
//  Pipeline (runs on agent thread)
// ─────────────────────────────────────────────────────────────────────────────

static void postStatus(AgentOrchestrator::StatusCallback& cb, GenerationStatus s)
{
    // Always post to message thread
    juce::MessageManager::callAsync([cb, s]{ cb(s); });
}

void AgentOrchestrator::runPipeline(
    std::string           userMessage,
    SongDocument          currentDoc,
    StatusCallback        statusCallback,
    TokenCallback         chatTokenCallback,
    DocCallback           docCallback)
{
    auto post = [&](GenerationStatus s){ postStatus(statusCallback, s); };

    try {
        // ── Stage 1: Chat ─────────────────────────────────────────────────────
        {
            GenerationStatus s;
            s.stage   = GenerationStatus::Stage::ChatProcessing;
            s.message = "IRA is thinking...";
            s.progressPercent = 5.0f;
            post(s);
        }

        ChatAgent   chatAgent(llm_);
        auto        intentJson = chatAgent.process(userMessage, currentDoc, chatTokenCallback);

        if (cancelled_.load()) return;

        // If it's just a chat reply (not a generate intent), we're done
        if (intentJson.value("type", "") != "generate" &&
            intentJson.value("type", "") != "regenerate")
        {
            // docCallback not called — UI just shows the chat reply
            return;
        }

        // ── Stage 2: Producer ─────────────────────────────────────────────────
        {
            GenerationStatus s;
            s.stage   = GenerationStatus::Stage::ProducerPlanning;
            s.message = "Planning arrangement...";
            s.progressPercent = 15.0f;
            post(s);
        }

        ProducerAgent producerAgent(llm_);
        auto          arrangementJson = producerAgent.plan(intentJson, currentDoc);

        if (cancelled_.load()) return;

        // Extract instrument list in priority order
        std::vector<std::string> instruments;
        if (arrangementJson.contains("tracks")) {
            // Sort by priority
            auto tracks = arrangementJson["tracks"].get<std::vector<json>>();
            std::sort(tracks.begin(), tracks.end(), [](const json& a, const json& b){
                return a.value("priority", 99) < b.value("priority", 99);
            });
            for (auto& t : tracks)
                instruments.push_back(t.value("instrument", ""));
        }

        // Apply generation order (drums first, then bass, etc.)
        std::vector<std::string> orderedInstruments;
        for (auto& ord : kGenerationOrder)
            if (std::find(instruments.begin(), instruments.end(), ord) != instruments.end())
                orderedInstruments.push_back(ord);
        // Any instruments not in kGenerationOrder go last
        for (auto& inst : instruments)
            if (std::find(orderedInstruments.begin(), orderedInstruments.end(), inst) == orderedInstruments.end())
                orderedInstruments.push_back(inst);

        // ── Stage 3: Conductor ────────────────────────────────────────────────
        {
            GenerationStatus s;
            s.stage   = GenerationStatus::Stage::ConductorBriefing;
            s.message = "Writing briefs for each instrument...";
            s.progressPercent = 25.0f;
            post(s);
        }

        ConductorAgent conductorAgent(llm_);
        auto           briefsJson = conductorAgent.brief(intentJson, arrangementJson);

        if (cancelled_.load()) return;

        // ── Stage 4: Track agents (sequential) ───────────────────────────────
        TrackAgent                 trackAgent(llm_);
        std::vector<json>          completedTracks;
        std::vector<Track>         newTracks;

        for (int i = 0; i < (int)orderedInstruments.size(); ++i) {
            if (cancelled_.load()) return;

            auto& inst = orderedInstruments[static_cast<size_t>(i)];

            {
                GenerationStatus s;
                s.stage             = GenerationStatus::Stage::TrackGenerating;
                s.message           = "Writing " + inst + "...";
                s.currentInstrument = inst;
                s.tracksComplete    = i;
                s.tracksTotal       = static_cast<int>(orderedInstruments.size());
                s.progressPercent   = 30.0f + (60.0f * i / orderedInstruments.size());
                post(s);
            }

            // Find this instrument's brief from conductor output
            json instBrief;
            if (briefsJson.contains("briefs")) {
                for (auto& b : briefsJson["briefs"])
                    if (b.value("instrument", "") == inst) { instBrief = b; break; }
            }

            // Run track agent — passes all previously written tracks for cohesion
            auto trackJson = trackAgent.compose(
                inst, instBrief, intentJson, completedTracks);

            completedTracks.push_back(trackJson);

            // Build a Track object from the JSON notes
            Track track;
            track.id         = SongDocument::newUUID();
            track.name       = juce::String(inst.c_str());
            track.instrument = juce::String(inst.c_str());
            // Assign channel (drums = 9, others sequential)
            track.midiChannel = (inst == "drums") ? 9 : (i % 9 == 9 ? 10 : i % 9);

            MidiClip clip;
            clip.id       = SongDocument::newUUID();
            clip.startBar = 0;
            clip.name     = juce::String(inst.c_str());

            if (trackJson.contains("notes")) {
                for (auto& nj : trackJson["notes"]) {
                    NoteEvent note;
                    note.pitch         = nj.value("pitch",         60);
                    note.startBeat     = nj.value("startBeat",     0.0f);
                    note.durationBeats = nj.value("durationBeats", 1.0f);
                    note.velocity      = nj.value("velocity",      80);
                    clip.notes.push_back(note);
                }
            }
            track.clips.push_back(std::move(clip));
            newTracks.push_back(std::move(track));
        }

        if (cancelled_.load()) return;

        // ── Stage 5: Build SongDocument ───────────────────────────────────────
        {
            GenerationStatus s;
            s.stage   = GenerationStatus::Stage::Building;
            s.message = "Assembling project...";
            s.progressPercent = 92.0f;
            post(s);
        }

        auto newDoc = std::make_shared<SongDocument>(currentDoc.clone());
        newDoc->mutableMetadata().bpm   = intentJson.value("bpm",  120.0f);
        newDoc->mutableMetadata().key   = juce::String(intentJson.value("key", "C major").c_str());
        newDoc->mutableMetadata().genre = juce::String(intentJson.value("genre", "").c_str());
        newDoc->mutableMetadata().vibe  = juce::String(intentJson.value("vibe",  "").c_str());
        newDoc->mutableMetadata().bars  = intentJson.value("bars",  8);

        // Replace all tracks with newly generated ones
        newDoc->mutableTracks() = std::move(newTracks);

        // Store last generation context for feedback
        lastGen_.vibe  = intentJson.value("vibe",  "");
        lastGen_.genre = intentJson.value("genre", "");
        lastGen_.bpm   = intentJson.value("bpm",   120.0f);
        lastGen_.key   = intentJson.value("key",   "C major");
        lastGen_.bars  = intentJson.value("bars",  8);
        lastGen_.instruments = orderedInstruments;

        {
            GenerationStatus s;
            s.stage   = GenerationStatus::Stage::Done;
            s.message = "Done!";
            s.progressPercent = 100.0f;
            post(s);
        }

        // Post result to message thread
        juce::MessageManager::callAsync([dcb = std::move(docCallback), newDoc]{
            dcb(newDoc);
        });

    } catch (const std::exception& e) {
        GenerationStatus s;
        s.stage   = GenerationStatus::Stage::Error;
        s.message = std::string("Error: ") + e.what();
        post(s);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
//  Feedback
// ─────────────────────────────────────────────────────────────────────────────

void AgentOrchestrator::recordFeedback(const std::string& ratingText,
                                        const std::string& explanation)
{
    // TODO: Implement agent memory save (port from Python agent_memory.py)
    // Save to ~/.aria-cpp/agent_memory.json
    juce::ignoreUnused(ratingText, explanation);
    juce::Logger::writeToLog("[AgentOrchestrator] Feedback: " +
        juce::String(ratingText.c_str()) + " — " + juce::String(explanation.c_str()));
}

} // namespace aria
