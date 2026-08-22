#pragma once

#include <juce_core/juce_core.h>
#include <filesystem>
#include <functional>
#include <memory>
#include <string>

namespace aria {

// ─────────────────────────────────────────────────────────────────────────────
//  LLMRuntime
//
//  Pimpl wrapper around llama.cpp.
//  All llama.cpp headers are confined to LLMRuntime.cpp — they never leak.
//
//  Threading: all infer*() calls are BLOCKING and must be called from the
//  agent thread (never the audio thread or message thread directly).
// ─────────────────────────────────────────────────────────────────────────────

class LLMRuntime {
public:
    struct Params {
        std::filesystem::path modelPath;
        int   contextSize   = 4096;
        int   threads       = 8;      // CPU threads for inference
        float temperature   = 0.7f;
        int   maxTokens     = 1024;
        bool  gpuOffload    = false;  // set true if Metal/CUDA available
        int   gpuLayers     = 0;      // number of layers to offload to GPU
    };

    explicit LLMRuntime(Params p);
    ~LLMRuntime();

    // Non-copyable
    LLMRuntime(const LLMRuntime&) = delete;
    LLMRuntime& operator=(const LLMRuntime&) = delete;

    // ── Inference ─────────────────────────────────────────────────────────────

    /**
     * Synchronous inference. Blocks until completion.
     * Returns the full generated text (excluding the prompts).
     * Returns empty string on error.
     */
    std::string infer(std::string_view systemPrompt,
                      std::string_view userPrompt);

    /**
     * Streaming inference. Calls tokenCallback once per generated token.
     * Blocks until completion.
     * tokenCallback is called on the agent thread.
     */
    void inferStream(std::string_view systemPrompt,
                     std::string_view userPrompt,
                     std::function<void(std::string_view token)> tokenCallback);

    /**
     * JSON-constrained inference using a GBNF grammar.
     * The grammar guarantees the output matches a JSON schema without retries.
     * Returns the full JSON string.
     */
    std::string inferJSON(std::string_view systemPrompt,
                          std::string_view userPrompt,
                          std::string_view gbnfGrammar);

    // ── Status ────────────────────────────────────────────────────────────────

    bool         isLoaded()  const noexcept;
    std::string  modelName() const;
    std::string  lastError() const;

    /** Cancel an in-progress inference (thread-safe). */
    void cancel() noexcept;

    // ── GBNF grammar helpers ──────────────────────────────────────────────────

    /** Returns the GBNF grammar string for constrained JSON output. */
    static std::string noteArrayGrammar();
    static std::string arrangementGrammar();
    static std::string intentGrammar();

private:
    struct Impl;                        // defined only in LLMRuntime.cpp
    std::unique_ptr<Impl> d_;
};

} // namespace aria
