#include "TrackAgent.h"
#include <juce_core/juce_core.h>

using json = nlohmann::json;

namespace aria {

TrackAgent::TrackAgent(LLMRuntime& llm) : llm_(llm) {}

std::string TrackAgent::buildSystemPrompt(int beatsPerBar) const
{
    return std::string(R"(You are a MIDI composition AI inside the ARIA DAW.
You write actual notes for one specific instrument.

Rules:
- Reply ONLY with valid JSON. No text before or after.
- Beat 0.0 = start of bar 1. Each bar = )") + std::to_string(beatsPerBar) + R"( beats.
- Pitch = MIDI note: C4=60, D4=62, E4=64, F4=65, G4=67, A4=69, B4=71.
- Velocity 1-127. 80=normal, 100=accented, 60=soft.
- Duration in beats: 0.25=16th, 0.5=8th, 1.0=quarter, 2.0=half, 4.0=whole.
- GM drums (MIDI ch 10): kick=36, snare=38, closed HH=42, open HH=46, crash=49.
- Do NOT clash with or double notes from already-written tracks.

Output: {"instrument":"<name>","notes":[{"pitch":<int>,"startBeat":<float>,"durationBeats":<float>,"velocity":<int>}],"summary":"<1 sentence>"})";
}

std::string TrackAgent::buildUserPrompt(
    const std::string&                 instrument,
    const json&                        brief,
    const json&                        intentJson,
    const std::vector<json>&           completedTracks) const
{
    std::string prompt;

    prompt += "CONDUCTOR BRIEF FOR " + instrument + ":\n";
    prompt += brief.dump(2) + "\n\n";

    prompt += "GLOBAL CONTEXT:\n";
    prompt += "Genre: "     + intentJson.value("genre", "")   + "\n";
    prompt += "BPM: "       + std::to_string(static_cast<int>(intentJson.value("bpm", 120.0f))) + "\n";
    prompt += "Key: "       + intentJson.value("key",   "C major") + "\n";
    prompt += "Bars: "      + std::to_string(intentJson.value("bars", 8)) + "\n";
    prompt += "Section: "   + intentJson.value("section", "verse") + "\n\n";

    if (!completedTracks.empty()) {
        prompt += "ALREADY WRITTEN — do NOT double or clash with these:\n";
        for (auto& t : completedTracks) {
            int noteCount = t.contains("notes") ? static_cast<int>(t["notes"].size()) : 0;
            std::string summary = t.value("summary", "");
            prompt += "  " + t.value("instrument", "?") + ": " +
                      std::to_string(noteCount) + " notes — " + summary + "\n";
        }
        prompt += "\n";
    }

    prompt += "Now write the notes for " + instrument + ".";
    return prompt;
}

json TrackAgent::compose(
    const std::string&   instrument,
    const json&          brief,
    const json&          intentJson,
    const std::vector<json>& completedTracks)
{
    int beatsPerBar = 4; // TODO: read from time signature

    auto systemPrompt = buildSystemPrompt(beatsPerBar);
    auto userPrompt   = buildUserPrompt(instrument, brief, intentJson, completedTracks);

    auto raw = llm_.inferJSON(systemPrompt, userPrompt, LLMRuntime::noteArrayGrammar());

    try {
        auto result = json::parse(raw);

        // Validate: if fewer than 4 notes, retry once
        if (!result.contains("notes") || result["notes"].size() < 4) {
            juce::Logger::writeToLog("[TrackAgent] Too few notes for " +
                juce::String(instrument.c_str()) + ", retrying...");

            auto retryPrompt = userPrompt + "\n\nYou only wrote " +
                std::to_string(result.contains("notes") ? result["notes"].size() : 0) +
                " notes. Please write a full " +
                std::to_string(intentJson.value("bars", 8)) + "-bar part.";

            raw = llm_.inferJSON(systemPrompt, retryPrompt, LLMRuntime::noteArrayGrammar());
            result = json::parse(raw);
        }

        return result;

    } catch (...) {
        juce::Logger::writeToLog("[TrackAgent] JSON parse failed for " +
            juce::String(instrument.c_str()) + ", using silence");
        return {
            {"instrument", instrument},
            {"notes",      json::array()},
            {"summary",    "Empty part (generation failed)"}
        };
    }
}

} // namespace aria
