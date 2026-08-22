#pragma once

#include "core/AudioEngine.h"
#include "agents/AgentOrchestrator.h"
#include "plugins/PluginHost.h"
#include <juce_gui_basics/juce_gui_basics.h>
#include <memory>

namespace aria {

class IRAPanel;
class PianoRollWindow;
class MixerPanel;

// ─────────────────────────────────────────────────────────────────────────────
//  MainWindow
//
//  Top-level JUCE DocumentWindow. Owns all subsystems:
//    AudioEngine, AgentOrchestrator, PluginHost, LLMRuntime.
//  Creates and lays out all UI panels.
// ─────────────────────────────────────────────────────────────────────────────

class MainWindow : public juce::DocumentWindow,
                   public juce::MenuBarModel
{
public:
    MainWindow(const juce::String& name,
               AudioEngine&        audioEngine,
               AgentOrchestrator&  orchestrator,
               PluginHost&         pluginHost);

    ~MainWindow() override;

    // ── DocumentWindow ────────────────────────────────────────────────────────
    void closeButtonPressed() override;

    // ── MenuBarModel ──────────────────────────────────────────────────────────
    juce::StringArray getMenuBarNames() override;
    juce::PopupMenu   getMenuForIndex(int topLevelMenuIndex, const juce::String& menuName) override;
    void              menuItemSelected(int menuItemID, int topLevelMenuIndex) override;

    // ── Document callbacks ────────────────────────────────────────────────────

    /** Called when the agent pipeline produces a new SongDocument. */
    void onNewDocumentGenerated(std::shared_ptr<SongDocument> doc);

    /** Called every ~50ms by a timer to update playhead. */
    void onPlaybackTick();

private:
    void setupLayout();
    void setupMenuBar();
    void setupKeyboardShortcuts();
    void setupTransportCallbacks();

    AudioEngine&       audioEngine_;
    AgentOrchestrator& orchestrator_;
    PluginHost&        pluginHost_;

    std::unique_ptr<juce::Component> contentComponent_;
    std::unique_ptr<IRAPanel>        iraPanel_;
    std::unique_ptr<MixerPanel>      mixerPanel_;
    std::unique_ptr<PianoRollWindow> pianoRoll_;
    std::unique_ptr<juce::MenuBarComponent> menuBar_;

    std::unique_ptr<juce::Timer>     playbackTimer_;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(MainWindow)
};

} // namespace aria
