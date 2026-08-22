#include "LLMRuntime.h"

// llama.cpp — included ONLY in this file (pimpl pattern)
#include <llama.h>
#include <grammar-parser.h>  // for GBNF grammar support

#include <juce_core/juce_core.h>
#include <atomic>
#include <string>
#include <stdexcept>

namespace aria {

// ─────────────────────────────────────────────────────────────────────────────
//  Pimpl implementation
// ─────────────────────────────────────────────────────────────────────────────

struct LLMRuntime::Impl {
    Params             params;
    llama_model*       model   = nullptr;
    llama_context*     ctx     = nullptr;
    std::atomic<bool>  cancel_ { false };
    std::string        lastError_;
    std::string        modelName_;

    Impl(Params p) : params(std::move(p)) { load(); }

    ~Impl() { unload(); }

    void load()
    {
        llama_backend_init(false);

        llama_model_params mparams = llama_model_default_params();
        mparams.n_gpu_layers = params.gpuOffload ? params.gpuLayers : 0;

        model = llama_load_model_from_file(
            params.modelPath.string().c_str(), mparams);

        if (!model) {
            lastError_ = "Failed to load model from: " + params.modelPath.string();
            return;
        }

        llama_context_params cparams = llama_context_default_params();
        cparams.n_ctx       = params.contextSize;
        cparams.n_threads   = params.threads;
        cparams.seed        = LLAMA_DEFAULT_SEED;

        ctx = llama_new_context_with_model(model, cparams);
        if (!ctx) {
            lastError_ = "Failed to create llama context";
            llama_free_model(model);
            model = nullptr;
            return;
        }

        modelName_ = llama_model_desc(model);
        juce::Logger::writeToLog("[LLMRuntime] Loaded model: " + juce::String(modelName_.c_str()));
    }

    void unload()
    {
        if (ctx)   { llama_free(ctx);         ctx   = nullptr; }
        if (model) { llama_free_model(model); model = nullptr; }
        llama_backend_free();
    }

    // Build a Qwen-style chat prompt (matches Qwen 2.5 Instruct template)
    std::string buildPrompt(std::string_view system, std::string_view user) const
    {
        std::string prompt;
        prompt += "<|im_start|>system\n";
        prompt += system;
        prompt += "<|im_end|>\n";
        prompt += "<|im_start|>user\n";
        prompt += user;
        prompt += "<|im_end|>\n";
        prompt += "<|im_start|>assistant\n";
        return prompt;
    }

    std::string runInference(const std::string& prompt,
                             llama_grammar* grammar,
                             std::function<void(std::string_view)> streamCb)
    {
        if (!model || !ctx) {
            lastError_ = "Model not loaded";
            return "";
        }

        cancel_.store(false);

        // Tokenise
        std::vector<llama_token> tokens(params.contextSize);
        int n = llama_tokenize(model,
                               prompt.c_str(),
                               static_cast<int32_t>(prompt.size()),
                               tokens.data(),
                               static_cast<int32_t>(tokens.size()),
                               /*add_bos=*/true,
                               /*special=*/true);
        if (n < 0) {
            lastError_ = "Tokenisation failed";
            return "";
        }
        tokens.resize(static_cast<size_t>(n));

        // KV cache reset
        llama_kv_cache_clear(ctx);

        // Decode input tokens
        llama_batch batch = llama_batch_get_one(tokens.data(), static_cast<int32_t>(tokens.size()), 0, 0);
        if (llama_decode(ctx, batch) != 0) {
            lastError_ = "llama_decode failed on prompt";
            return "";
        }

        // Sampling params
        llama_sampler_chain_params sparams = llama_sampler_chain_default_params();
        llama_sampler* smpl = llama_sampler_chain_init(sparams);
        llama_sampler_chain_add(smpl, llama_sampler_init_temp(params.temperature));
        llama_sampler_chain_add(smpl, llama_sampler_init_top_p(0.9f, 1));
        if (grammar)
            llama_sampler_chain_add(smpl, llama_sampler_init_grammar(model, grammar, "root"));
        llama_sampler_chain_add(smpl, llama_sampler_init_dist(LLAMA_DEFAULT_SEED));

        std::string result;
        result.reserve(2048);

        for (int i = 0; i < params.maxTokens; ++i) {
            if (cancel_.load()) break;

            llama_token id = llama_sampler_sample(smpl, ctx, -1);
            llama_sampler_accept(smpl, id);

            if (llama_token_is_eog(model, id)) break;

            // Decode token to text
            char buf[64] = {};
            int  len     = llama_token_to_piece(model, id, buf, sizeof(buf), 0, true);
            if (len < 0) break;

            std::string_view piece(buf, static_cast<size_t>(len));
            result.append(piece);

            if (streamCb) streamCb(piece);

            // Continue decoding
            llama_batch next = llama_batch_get_one(&id, 1, static_cast<int32_t>(tokens.size()) + i, 0);
            if (llama_decode(ctx, next) != 0) break;
        }

        llama_sampler_free(smpl);
        return result;
    }
};

// ─────────────────────────────────────────────────────────────────────────────
//  LLMRuntime public interface
// ─────────────────────────────────────────────────────────────────────────────

LLMRuntime::LLMRuntime(Params p)
    : d_(std::make_unique<Impl>(std::move(p)))
{
}

LLMRuntime::~LLMRuntime() = default;

bool LLMRuntime::isLoaded() const noexcept
{
    return d_->model != nullptr && d_->ctx != nullptr;
}

std::string LLMRuntime::modelName() const { return d_->modelName_; }
std::string LLMRuntime::lastError()  const { return d_->lastError_; }

void LLMRuntime::cancel() noexcept { d_->cancel_.store(true); }

std::string LLMRuntime::infer(std::string_view systemPrompt,
                               std::string_view userPrompt)
{
    auto prompt = d_->buildPrompt(systemPrompt, userPrompt);
    return d_->runInference(prompt, nullptr, nullptr);
}

void LLMRuntime::inferStream(std::string_view systemPrompt,
                              std::string_view userPrompt,
                              std::function<void(std::string_view)> tokenCallback)
{
    auto prompt = d_->buildPrompt(systemPrompt, userPrompt);
    d_->runInference(prompt, nullptr, std::move(tokenCallback));
}

std::string LLMRuntime::inferJSON(std::string_view systemPrompt,
                                   std::string_view userPrompt,
                                   std::string_view gbnfGrammar)
{
    // Parse GBNF grammar
    auto grammar_str = std::string(gbnfGrammar);
    // grammar-parser.h API — creates a grammar that constrains output
    // Note: the exact API may vary by llama.cpp version; adjust as needed.
    auto parsed = grammar_parser::parse(grammar_str.c_str());
    llama_grammar* g = nullptr;
    if (!parsed.rules.empty()) {
        std::vector<const llama_grammar_element*> ptrs;
        ptrs.reserve(parsed.rules.size());
        for (auto& rule : parsed.rules) ptrs.push_back(rule.data());
        g = llama_grammar_init(ptrs.data(),
                               ptrs.size(),
                               parsed.symbol_ids.at("root"));
    }

    auto prompt = d_->buildPrompt(systemPrompt, userPrompt);
    auto result = d_->runInference(prompt, g, nullptr);

    if (g) llama_grammar_free(g);
    return result;
}

// ─────────────────────────────────────────────────────────────────────────────
//  GBNF Grammars
// ─────────────────────────────────────────────────────────────────────────────

std::string LLMRuntime::noteArrayGrammar()
{
    // Constrains output to:
    // {"instrument":"...","notes":[{"pitch":N,"startBeat":N,"durationBeats":N,"velocity":N}],"summary":"..."}
    return R"(
root   ::= "{" ws "\"instrument\"" ws ":" ws string ws "," ws "\"notes\"" ws ":" ws note-array ws "," ws "\"summary\"" ws ":" ws string ws "}"
note-array ::= "[" ws (note ("," ws note)*)? ws "]"
note   ::= "{" ws "\"pitch\"" ws ":" ws integer ws "," ws "\"startBeat\"" ws ":" ws number ws "," ws "\"durationBeats\"" ws ":" ws number ws "," ws "\"velocity\"" ws ":" ws integer ws "}"
string ::= "\"" ([^"\\] | "\\" .)* "\""
integer ::= [0-9]+
number  ::= [0-9]+ ("." [0-9]+)?
ws      ::= [ \t\n\r]*
)";
}

std::string LLMRuntime::arrangementGrammar()
{
    return R"(
root ::= "{" ws "\"section\"" ws ":" ws string ws "," ws "\"overallStyle\"" ws ":" ws string ws "," ws "\"tracks\"" ws ":" ws track-array ws "}"
track-array ::= "[" ws (track ("," ws track)*)? ws "]"
track ::= "{" ws "\"instrument\"" ws ":" ws string ws "," ws "\"role\"" ws ":" ws string ws "," ws "\"style\"" ws ":" ws string ws "," ws "\"density\"" ws ":" ws density ws "," ws "\"priority\"" ws ":" ws integer ws "}"
density ::= "\"sparse\"" | "\"medium\"" | "\"dense\""
string  ::= "\"" ([^"\\] | "\\" .)* "\""
integer ::= [0-9]+
ws      ::= [ \t\n\r]*
)";
}

std::string LLMRuntime::intentGrammar()
{
    return R"(
root ::= "{" ws "\"type\"" ws ":" ws intent-type ws "," ws members ws "}"
intent-type ::= "\"generate\"" | "\"chat\"" | "\"feedback\"" | "\"regenerate\"" | "\"stop\""
members ::= member ("," ws member)*
member  ::= string ws ":" ws value
value   ::= string | number | integer | "true" | "false" | "null" | array | object
array   ::= "[" ws (value ("," ws value)*)? ws "]"
object  ::= "{" ws (member ("," ws member)*)? ws "}"
string  ::= "\"" ([^"\\] | "\\" .)* "\""
number  ::= [0-9]+ ("." [0-9]+)?
integer ::= [0-9]+
ws      ::= [ \t\n\r]*
)";
}

} // namespace aria
