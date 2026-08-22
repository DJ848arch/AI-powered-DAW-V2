#include "ProducerAgent.h"
#include <juce_core/juce_core.h>

using json = nlohmann::json;

namespace aria {

ProducerAgent::ProducerAgent(LLMRuntime& llm) : llm_(llm) {}

json ProducerAgent::plan(const json& intentJson, const SongDocument& /*doc*/)
{
    std::string systemPrompt = R"(You are a professional music producer AI inside the ARIA DAW.
You receive a brief and return a JSON arrangement plan.
Rules: Reply ONLY with valid JSON. Choose 3-7 instruments. For each, describe its role.
Output: {"section":"<name>","overallStyle":"<description>","tracks":[{"instrument":"<name>","role":"<1 sentence>","style":"<description>","density":"sparse"|"medium"|"dense","priority":<1-8>}]})";

    std::string userPrompt = "BRIEF:\n" + intentJson.dump(2);

    auto raw = llm_.inferJSON(systemPrompt, userPrompt, LLMRuntime::arrangementGrammar());

    try {
        return json::parse(raw);
    } catch (...) {
        juce::Logger::writeToLog("[ProducerAgent] Failed to parse JSON");
        // Fallback: simple drums + bass + piano
        return {
            {"section", "verse"},
            {"overallStyle", "Simple arrangement"},
            {"tracks", json::array({
                {{"instrument","drums"},{"role","Basic beat"},{"style","straight"},{"density","medium"},{"priority",1}},
                {{"instrument","bass"}, {"role","Root notes"},{"style","simple"}, {"density","sparse"}, {"priority",2}},
                {{"instrument","piano"},{"role","Chords"},    {"style","comping"},{"density","medium"},{"priority",3}}
            })}
        };
    }
}

} // namespace aria
