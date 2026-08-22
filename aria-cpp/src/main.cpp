/**
 * ARIA-CPP — AI-Assisted DAW
 *
 * Entry point. Boots JUCE, initialises all subsystems, and opens the main window.
 *
 * Startup sequence:
 *   1. AudioEngine::initialise()     — Tracktion Engine + audio device
 *   2. LLMRuntime constructor        — loads Qwen 2.5 7B from resources/models/
 *   3. AgentOrchestrator constructor — wires LLM to agents
 *   4. PluginHost::loadCachedRegistry() — restore last plugin scan
 *   5. MainWindow constructor        — creates all UI panels
 */

#include "core/AudioEngine.h"
#include "llm/LLMRuntime.h"
#include "agents/AgentOrchestrator.h"
#include "plugins/PluginHost.h"
#include "ui/MainWindow.h"

#include <juce_core/juce_core.h>
#include <juce_gui_basics/juce_gui_basics.h>

using namespace aria;

// ─────────────────────────────────────────────────────────────────────────────
//  AriaApplication
// ─────────────────────────────────────────────────────────────────────────────

class AriaApplication : public juce::JUCEApplication {
public:
    const juce::String getApplicationName()    override { return "ARIA"; }
    const juce::String getApplicationVersion() override { return "0.1.0"; }
    bool               moreThanOneInstanceAllowed() override { return false; }

    void initialise(const juce::String& /*commandLine*/) override
    {
        // ── 1. Audio engine ───────────────────────────────────────────────────
        audioEngine_ = std::make_unique<AudioEngine>();
        if (!audioEngine_->initialise()) {
            juce::Logger::writeToLog("[ARIA] AudioEngine init failed — continuing without audio");
        }

        // ── 2. LLM runtime ────────────────────────────────────────────────────
        auto modelPath = findModelPath();
        if (modelPath.isEmpty()) {
            juce::Logger::writeToLog("[ARIA] WARNING: No model file found in resources/models/");
            juce::Logger::writeToLog("[ARIA] Place Qwen 2.5 7B Instruct Q4_K_M .gguf there to enable AI features");
        }

        LLMRuntime::Params llmParams;
        llmParams.modelPath   = modelPath.toStdString();
        llmParams.contextSize = 4096;
        llmParams.threads     = juce::SystemStats::getNumCpus();
        llmParams.temperature = 0.7f;
        llmParams.maxTokens   = 1024;
        llmRuntime_ = std::make_unique<LLMRuntime>(std::move(llmParams));

        if (!llmRuntime_->isLoaded())
            juce::Logger::writeToLog("[ARIA] LLM not loaded: " + juce::String(llmRuntime_->lastError().c_str()));
        else
            juce::Logger::writeToLog("[ARIA] Model loaded: " + juce::String(llmRuntime_->modelName().c_str()));

        // ── 3. Agent orchestrator ─────────────────────────────────────────────
        orchestrator_ = std::make_unique<AgentOrchestrator>(*llmRuntime_);

        // ── 4. Plugin host ────────────────────────────────────────────────────
        pluginHost_ = std::make_unique<PluginHost>();
        pluginHost_->loadCachedRegistry();

        // ── 5. Main window ────────────────────────────────────────────────────
        mainWindow_ = std::make_unique<MainWindow>(
            getApplicationName(),
            *audioEngine_,
            *orchestrator_,
            *pluginHost_
        );
    }

    void shutdown() override
    {
        mainWindow_.reset();
        orchestrator_.reset();
        llmRuntime_.reset();
        audioEngine_.reset();
        pluginHost_.reset();
    }

    void systemRequestedQuit() override { quit(); }
    void anotherInstanceStarted(const juce::String&) override {}
    void suspended() override {}
    void resumed() override {}
    void unhandledException(const std::exception* e,
                            const juce::String& /*file*/,
                            int /*line*/) override
    {
        if (e)
            juce::Logger::writeToLog("[ARIA] Unhandled exception: " + juce::String(e->what()));
    }

private:
    juce::String findModelPath()
    {
        // Look for any .gguf file in resources/models/ relative to the app
        auto appDir = juce::File::getSpecialLocation(juce::File::currentApplicationFile)
                          .getParentDirectory();

        // Try several locations
        std::vector<juce::File> searchPaths = {
            appDir.getChildFile("resources/models"),
            appDir.getParentDirectory().getChildFile("resources/models"),
            juce::File::getSpecialLocation(juce::File::userHomeDirectory)
                .getChildFile(".aria-cpp/models"),
        };

        for (auto& dir : searchPaths) {
            if (!dir.isDirectory()) continue;
            auto files = dir.findChildFiles(juce::File::findFiles, false, "*.gguf");
            if (!files.isEmpty()) {
                // Prefer Qwen 2.5 if multiple models
                for (auto& f : files)
                    if (f.getFileName().containsIgnoreCase("qwen") ||
                        f.getFileName().containsIgnoreCase("Q4_K_M"))
                        return f.getFullPathName();
                return files[0].getFullPathName();
            }
        }
        return {};
    }

    std::unique_ptr<AudioEngine>       audioEngine_;
    std::unique_ptr<LLMRuntime>        llmRuntime_;
    std::unique_ptr<AgentOrchestrator> orchestrator_;
    std::unique_ptr<PluginHost>        pluginHost_;
    std::unique_ptr<MainWindow>        mainWindow_;
};

// ─────────────────────────────────────────────────────────────────────────────
//  JUCE application entry point macro
// ─────────────────────────────────────────────────────────────────────────────

START_JUCE_APPLICATION(AriaApplication)
