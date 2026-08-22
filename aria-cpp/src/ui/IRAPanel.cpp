#include "IRAPanel.h"
#include "core/SongDocument.h"

namespace aria {

IRAPanel::IRAPanel(AgentOrchestrator& orchestrator)
    : orchestrator_(orchestrator),
      progressBar_(progressValue_)
{
    // Title
    titleLabel_.setText("IRA", juce::dontSendNotification);
    titleLabel_.setFont(juce::Font(18.0f, juce::Font::bold));
    addAndMakeVisible(titleLabel_);

    // Chat history (read-only, scrollable)
    chatHistory_.setMultiLine(true);
    chatHistory_.setReadOnly(true);
    chatHistory_.setScrollbarsShown(true);
    chatHistory_.setFont(juce::Font(13.0f));
    addAndMakeVisible(chatHistory_);

    // Input box
    inputBox_.setMultiLine(false);
    inputBox_.setReturnKeyStartsNewLine(false);
    inputBox_.addListener(this);
    inputBox_.setTextToShowWhenEmpty("Ask IRA to make music...", juce::Colours::grey);
    addAndMakeVisible(inputBox_);

    // Send button
    sendButton_.onClick = [this]{ sendUserMessage(); };
    addAndMakeVisible(sendButton_);

    // Progress bar (hidden by default)
    progressBar_.setVisible(false);
    addAndMakeVisible(progressBar_);

    // Welcome message
    appendMessage("IRA", "Hey! I'm IRA, your AI music assistant. Tell me what you want to make.");
}

void IRAPanel::resized()
{
    auto area = getLocalBounds().reduced(8);

    titleLabel_.setBounds(area.removeFromTop(28));
    progressBar_.setBounds(area.removeFromTop(20));
    area.removeFromTop(4);

    auto inputArea = area.removeFromBottom(36);
    sendButton_.setBounds(inputArea.removeFromRight(60));
    inputBox_.setBounds(inputArea);

    chatHistory_.setBounds(area);
}

void IRAPanel::paint(juce::Graphics& g)
{
    g.fillAll(juce::Colour(0xff1e1e2e));
}

void IRAPanel::appendMessage(const juce::String& speaker, const juce::String& text)
{
    juce::MessageManager::callAsync([this, speaker, text] {
        auto current = chatHistory_.getText();
        if (current.isNotEmpty()) current += "\n\n";
        current += speaker + ": " + text;
        chatHistory_.setText(current);
        chatHistory_.moveCaretToEnd();
    });
}

void IRAPanel::streamToken(std::string_view token)
{
    juce::MessageManager::callAsync([this, tok = std::string(token)] {
        chatHistory_.moveCaretToEnd();
        chatHistory_.insertTextAtCaret(juce::String(tok.c_str()));
    });
}

void IRAPanel::setProgress(float pct, const juce::String& status)
{
    juce::MessageManager::callAsync([this, pct, status] {
        progressValue_ = static_cast<double>(pct) / 100.0;
        progressBar_.setVisible(pct > 0 && pct < 100);
        if (pct > 0 && pct < 100)
            appendMessage("IRA", status);
    });
}

void IRAPanel::onGenerationComplete(const juce::String& reply)
{
    appendMessage("IRA", reply);
    // Trigger feedback collection
    juce::Timer::callAfterDelay(800, [this]{
        appendMessage("IRA", "What did you think? 😊 (great / ok / not quite)");
        feedbackState_ = FeedbackState::AwaitingRating;
    });
}

void IRAPanel::textEditorReturnKeyPressed(juce::TextEditor& /*ed*/)
{
    sendUserMessage();
}

void IRAPanel::sendUserMessage()
{
    auto text = inputBox_.getText().trim();
    if (text.isEmpty()) return;
    inputBox_.clear();

    appendMessage("You", text);

    // Handle feedback state machine
    if (feedbackState_ == FeedbackState::AwaitingRating) {
        pendingRating_ = text;
        feedbackState_ = FeedbackState::AwaitingExplanation;
        appendMessage("IRA", "Thanks! Can you tell me a bit more about what you liked or didn't like?");
        return;
    }

    if (feedbackState_ == FeedbackState::AwaitingExplanation) {
        auto rating      = pendingRating_;
        auto explanation = text;
        feedbackState_   = FeedbackState::Idle;
        orchestrator_.recordFeedback(rating.toStdString(), explanation.toStdString());
        appendMessage("IRA", "Got it — I'll remember that for next time! 🧠");
        return;
    }

    // Normal generation
    // Get current doc from AudioEngine (TODO: inject reference)
    SongDocument emptyDoc;

    orchestrator_.generateFromUserMessage(
        text.toStdString(),
        emptyDoc,
        [this](GenerationStatus s) {
            setProgress(s.progressPercent, juce::String(s.message.c_str()));
            if (s.stage == GenerationStatus::Stage::Done)
                setProgress(0, {});
        },
        [this](std::string_view token) {
            streamToken(token);
        },
        [this](std::shared_ptr<SongDocument> /*doc*/) {
            onGenerationComplete("Here's your track! How does it feel?");
        }
    );
}

} // namespace aria
