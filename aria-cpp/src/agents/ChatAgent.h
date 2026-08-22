#pragma once

#include "llm/LLMRuntime.h"
#include "core/SongDocument.h"
#include <nlohmann/json.hpp>
#include <functional>
#include <string>

namespace aria {

class ChatAgent {
public:
    explicit ChatAgent(LLMRuntime& llm);

    /**
     * Process a user message and return an intent JSON object.
     * tokenCallback is called for each streamed token (for live UI display).
     */
    nlohmann::json process(
        const std::string&                              userMessage,
        const SongDocument&                             currentDoc,
        std::function<void(std::string_view)>           tokenCallback = nullptr
    );

private:
    std::string buildSystemPrompt(const SongDocument& doc) const;
    LLMRuntime& llm_;
};

} // namespace aria
