#pragma once
#include "llm/LLMRuntime.h"
#include <nlohmann/json.hpp>

namespace aria {
class ConductorAgent {
public:
    explicit ConductorAgent(LLMRuntime& llm);
    nlohmann::json brief(const nlohmann::json& intentJson,
                         const nlohmann::json& arrangementJson);
private:
    LLMRuntime& llm_;
};
} // namespace aria
