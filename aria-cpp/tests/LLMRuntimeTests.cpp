#include <catch2/catch_test_macros.hpp>
#include "llm/LLMRuntime.h"

using namespace aria;

// NOTE: These tests require a valid model file at resources/models/*.gguf
// They are marked [slow] so they can be excluded from CI with: ctest -E slow

TEST_CASE("LLMRuntime fails gracefully on missing model", "[LLMRuntime]")
{
    LLMRuntime::Params p;
    p.modelPath = "/nonexistent/path/model.gguf";

    LLMRuntime llm(p);
    REQUIRE_FALSE(llm.isLoaded());
    REQUIRE_FALSE(llm.lastError().empty());
}

TEST_CASE("LLMRuntime infer returns empty string when not loaded", "[LLMRuntime]")
{
    LLMRuntime::Params p;
    p.modelPath = "/nonexistent/path/model.gguf";
    LLMRuntime llm(p);

    auto result = llm.infer("system", "user");
    REQUIRE(result.empty());
}

TEST_CASE("LLMRuntime GBNF grammars are non-empty", "[LLMRuntime]")
{
    REQUIRE_FALSE(LLMRuntime::noteArrayGrammar().empty());
    REQUIRE_FALSE(LLMRuntime::arrangementGrammar().empty());
    REQUIRE_FALSE(LLMRuntime::intentGrammar().empty());
}

// Integration test (needs real model — run with: ctest -R "integration" -V)
// Enable by setting ARIA_MODEL_PATH environment variable
TEST_CASE("LLMRuntime live inference produces JSON", "[LLMRuntime][integration][slow]")
{
    const char* modelPath = std::getenv("ARIA_MODEL_PATH");
    if (!modelPath) {
        SKIP("Set ARIA_MODEL_PATH to run live inference tests");
    }

    LLMRuntime::Params p;
    p.modelPath   = modelPath;
    p.maxTokens   = 256;
    p.temperature = 0.1f;  // low temp for deterministic tests

    LLMRuntime llm(p);
    REQUIRE(llm.isLoaded());

    auto result = llm.inferJSON(
        "You are a JSON API. Reply ONLY with valid JSON.",
        "Return: {\"status\": \"ok\"}",
        LLMRuntime::intentGrammar()
    );

    REQUIRE_FALSE(result.empty());

    // Should be parseable JSON
    REQUIRE_NOTHROW([&]{ nlohmann::json::parse(result); }());
}
