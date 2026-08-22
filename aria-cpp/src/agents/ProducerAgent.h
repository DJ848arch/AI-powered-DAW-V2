#pragma once
#include "llm/LLMRuntime.h"
#include "core/SongDocument.h"
#include <nlohmann/json.hpp>

namespace aria {
class ProducerAgent {
public:
    explicit ProducerAgent(LLMRuntime& llm);
    nlohmann::json plan(const nlohmann::json& intentJson, const SongDocument& doc);
private:
    LLMRuntime& llm_;
};
} // namespace aria
