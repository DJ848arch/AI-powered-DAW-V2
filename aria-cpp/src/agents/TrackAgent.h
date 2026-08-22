#pragma once
#include "llm/LLMRuntime.h"
#include <nlohmann/json.hpp>
#include <string>
#include <vector>

namespace aria {
class TrackAgent {
public:
    explicit TrackAgent(LLMRuntime& llm);

    /**
     * Compose notes for one instrument.
     * completedTracks contains all previously generated tracks (for cohesion).
     * Returns JSON: {"instrument":"...","notes":[...],"summary":"..."}
     */
    nlohmann::json compose(
        const std::string&              instrument,
        const nlohmann::json&           brief,
        const nlohmann::json&           intentJson,
        const std::vector<nlohmann::json>& completedTracks
    );

private:
    std::string buildSystemPrompt(int beatsPerBar) const;
    std::string buildUserPrompt(
        const std::string&              instrument,
        const nlohmann::json&           brief,
        const nlohmann::json&           intentJson,
        const std::vector<nlohmann::json>& completedTracks
    ) const;

    LLMRuntime& llm_;
};
} // namespace aria
