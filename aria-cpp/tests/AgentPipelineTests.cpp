#include <catch2/catch_test_macros.hpp>
#include "agents/ChatAgent.h"
#include "agents/ProducerAgent.h"
#include "agents/ConductorAgent.h"
#include "agents/TrackAgent.h"
#include "core/SongDocument.h"

using namespace aria;
using json = nlohmann::json;

// ─────────────────────────────────────────────────────────────────────────────
//  Mock LLMRuntime for unit testing agents without a real model
// ─────────────────────────────────────────────────────────────────────────────

class MockLLMRuntime : public LLMRuntime {
public:
    MockLLMRuntime() : LLMRuntime(makeParams()) {}

    std::string lastSystemPrompt;
    std::string lastUserPrompt;
    std::string nextResponse;

    // Override: return canned response instead of running inference
    std::string infer(std::string_view sys, std::string_view usr) {
        lastSystemPrompt = sys;
        lastUserPrompt   = usr;
        return nextResponse;
    }
    std::string inferJSON(std::string_view sys, std::string_view usr, std::string_view /*grammar*/) {
        return infer(sys, usr);
    }

private:
    static Params makeParams() {
        Params p;
        p.modelPath = "/dev/null"; // will fail to load — that's ok, we override
        return p;
    }
};

// ─────────────────────────────────────────────────────────────────────────────
//  ChatAgent tests
// ─────────────────────────────────────────────────────────────────────────────

TEST_CASE("ChatAgent parses generate intent JSON", "[ChatAgent]")
{
    MockLLMRuntime llm;
    llm.nextResponse = R"({
        "type": "generate",
        "reply": "Making a lo-fi beat!",
        "vibe": "rainy afternoon",
        "genre": "lo-fi hip hop",
        "bpm": 78,
        "key": "A minor",
        "bars": 4,
        "instruments": ["drums", "bass", "piano", "pad"]
    })";

    ChatAgent agent(llm);
    auto intent = agent.process("make me a chill lo-fi beat", SongDocument::empty());

    REQUIRE(intent["type"] == "generate");
    REQUIRE(intent["bpm"] == 78);
    REQUIRE(intent["genre"] == "lo-fi hip hop");
    REQUIRE(intent["instruments"].size() == 4);
}

TEST_CASE("ChatAgent handles malformed JSON gracefully", "[ChatAgent]")
{
    MockLLMRuntime llm;
    llm.nextResponse = "this is not json at all";

    ChatAgent agent(llm);
    auto intent = agent.process("hey", SongDocument::empty());

    // Should return a chat type fallback
    REQUIRE(intent.contains("type"));
    REQUIRE(intent["type"] == "chat");
}

// ─────────────────────────────────────────────────────────────────────────────
//  ProducerAgent tests
// ─────────────────────────────────────────────────────────────────────────────

TEST_CASE("ProducerAgent parses arrangement JSON", "[ProducerAgent]")
{
    MockLLMRuntime llm;
    llm.nextResponse = R"({
        "section": "verse",
        "overallStyle": "Sparse lo-fi",
        "tracks": [
            {"instrument":"drums","role":"Basic beat","style":"swung","density":"sparse","priority":1},
            {"instrument":"bass", "role":"Root notes","style":"muted", "density":"sparse","priority":2}
        ]
    })";

    ProducerAgent agent(llm);
    json intent = {{"bpm", 78}, {"key", "A minor"}, {"bars", 4}, {"genre", "lo-fi"}};
    auto plan = agent.plan(intent, SongDocument::empty());

    REQUIRE(plan["section"] == "verse");
    REQUIRE(plan["tracks"].size() == 2);
    REQUIRE(plan["tracks"][0]["instrument"] == "drums");
}

TEST_CASE("ProducerAgent falls back on bad JSON", "[ProducerAgent]")
{
    MockLLMRuntime llm;
    llm.nextResponse = "```json oops```";

    ProducerAgent agent(llm);
    json intent = {{"bpm", 120}, {"key", "C major"}, {"bars", 8}};
    auto plan = agent.plan(intent, SongDocument::empty());

    // Should return a valid fallback plan with at least drums, bass, piano
    REQUIRE(plan.contains("tracks"));
    REQUIRE(plan["tracks"].size() >= 3);
}

// ─────────────────────────────────────────────────────────────────────────────
//  TrackAgent tests
// ─────────────────────────────────────────────────────────────────────────────

TEST_CASE("TrackAgent parses note JSON correctly", "[TrackAgent]")
{
    MockLLMRuntime llm;
    llm.nextResponse = R"({
        "instrument": "drums",
        "notes": [
            {"pitch": 36, "startBeat": 0.0, "durationBeats": 0.25, "velocity": 100},
            {"pitch": 38, "startBeat": 1.0, "durationBeats": 0.25, "velocity": 90},
            {"pitch": 42, "startBeat": 0.0, "durationBeats": 0.25, "velocity": 70},
            {"pitch": 42, "startBeat": 0.5, "durationBeats": 0.25, "velocity": 65}
        ],
        "summary": "Basic kick and snare pattern"
    })";

    TrackAgent agent(llm);
    json intent = {{"bpm", 78}, {"key", "A minor"}, {"bars", 4}, {"section", "verse"}};
    json brief  = {{"instrument", "drums"}, {"brief", "Play a basic beat"}};

    auto result = agent.compose("drums", brief, intent, {});

    REQUIRE(result["instrument"] == "drums");
    REQUIRE(result["notes"].size() == 4);
    REQUIRE(result["notes"][0]["pitch"] == 36);
    REQUIRE(result["summary"] == "Basic kick and snare pattern");
}

TEST_CASE("TrackAgent includes completed_tracks context in prompt", "[TrackAgent]")
{
    MockLLMRuntime llm;
    llm.nextResponse = R"({"instrument":"bass","notes":[
        {"pitch":45,"startBeat":0.0,"durationBeats":2.0,"velocity":85},
        {"pitch":45,"startBeat":4.0,"durationBeats":2.0,"velocity":80},
        {"pitch":43,"startBeat":8.0,"durationBeats":2.0,"velocity":80},
        {"pitch":45,"startBeat":12.0,"durationBeats":2.0,"velocity":75}
    ],"summary":"Simple root note bass line"})";

    TrackAgent agent(llm);
    json intent = {{"bpm", 78}, {"bars", 4}, {"key", "A minor"}, {"section", "verse"}};
    json brief  = {{"instrument", "bass"}, {"brief", "Play root notes"}};

    std::vector<json> completed = {{
        {"instrument", "drums"},
        {"notes",      json::array()},
        {"summary",    "Basic lo-fi beat"}
    }};

    auto result = agent.compose("bass", brief, intent, completed);

    REQUIRE(result["instrument"] == "bass");
    REQUIRE(result["notes"].size() == 4);

    // Verify the completed track was mentioned in the prompt
    REQUIRE(llm.lastUserPrompt.find("drums") != std::string::npos);
    REQUIRE(llm.lastUserPrompt.find("ALREADY WRITTEN") != std::string::npos);
}
