#include "ConductorAgent.h"
#include <juce_core/juce_core.h>

using json = nlohmann::json;

namespace aria {

ConductorAgent::ConductorAgent(LLMRuntime& llm) : llm_(llm) {}

json ConductorAgent::brief(const json& intentJson, const json& arrangementJson)
{
    std::string systemPrompt = R"(You are the conductor AI inside the ARIA DAW.
You receive an arrangement plan and produce musical briefs for each track agent.
Rules: Reply ONLY with valid JSON.
Output: {"globalNotes":"<overall guidance>","briefs":[{"instrument":"<name>","section":"<name>","brief":"<2-4 sentence directions>","pitchRange":"<range or null>","rhythmicFeel":"<description>","relationship":"<how it relates to others>"}]})";

    std::string userPrompt =
        "ARRANGEMENT:\n" + arrangementJson.dump(2) +
        "\n\nINTENT:\n" + intentJson.dump(2);

    auto raw = llm_.infer(systemPrompt, userPrompt);

    try {
        return json::parse(raw);
    } catch (...) {
        juce::Logger::writeToLog("[ConductorAgent] Failed to parse JSON, using empty briefs");
        json briefs = json::array();
        if (arrangementJson.contains("tracks")) {
            for (auto& t : arrangementJson["tracks"]) {
                briefs.push_back({
                    {"instrument", t.value("instrument", "unknown")},
                    {"section",    intentJson.value("section", "verse")},
                    {"brief",      t.value("role", "Play your part.")},
                    {"pitchRange", nullptr},
                    {"rhythmicFeel", t.value("style", "")},
                    {"relationship", "Support the other instruments."}
                });
            }
        }
        return {{"globalNotes", "Play musically."}, {"briefs", briefs}};
    }
}

} // namespace aria
