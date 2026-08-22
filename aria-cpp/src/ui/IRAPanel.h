#pragma once
#include "agents/AgentOrchestrator.h"
#include <juce_gui_basics/juce_gui_basics.h>
#include <juce_gui_extra/juce_gui_extra.h>

namespace aria {

// ─────────────────────────────────────────────────────────────────────────────
//  IRAPanel — AI assistant chat sidebar
// ─────────────────────────────────────────────────────────────────────────────

class IRAPanel : public juce::Component,
                 private juce::TextEditor::Listener
{
public:
    explicit IRAPanel(AgentOrchestrator& orchestrator);
    ~IRAPanel() override = default;

    void resized() override;
    void paint(juce::Graphics& g) override;

    /** Append a message to the chat history. */
    void appendMessage(const juce::String& speaker, const juce::String& text);

    /** Stream a token into the last assistant message. */
    void streamToken(std::string_view token);

    /** Show the generation progress bar. */
    void setProgress(float pct, const juce::String& status);

    /** Called when a new document is generated — triggers "What did you think?" */
    void onGenerationComplete(const juce::String& reply);

private:
    void textEditorReturnKeyPressed(juce::TextEditor&) override;
    void sendUserMessage();

    AgentOrchestrator& orchestrator_;

    juce::TextEditor  chatHistory_;
    juce::TextEditor  inputBox_;
    juce::TextButton  sendButton_ { "Send" };
    juce::Label       titleLabel_;
    juce::ProgressBar progressBar_;
    double            progressValue_ = 0.0;

    // Feedback state
    enum class FeedbackState { Idle, AwaitingRating, AwaitingExplanation };
    FeedbackState  feedbackState_ = FeedbackState::Idle;
    juce::String   pendingRating_;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(IRAPanel)
};

} // namespace aria
