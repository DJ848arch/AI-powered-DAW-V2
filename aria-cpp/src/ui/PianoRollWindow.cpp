#include "PianoRollWindow.h"

namespace aria {

static constexpr int kPianoKeyWidth = 40;
static constexpr int kHeaderHeight  = 20;
static constexpr int kMidiPitchMax  = 127;
static constexpr int kMidiPitchMin  = 0;

PianoRollWindow::PianoRollWindow()
{
    addAndMakeVisible(hScrollBar_);
    hScrollBar_.addListener(this);
    setOpaque(true);
}

void PianoRollWindow::resized()
{
    auto area = getLocalBounds();
    hScrollBar_.setBounds(area.removeFromBottom(12));
}

void PianoRollWindow::paint(juce::Graphics& g)
{
    g.fillAll(juce::Colour(0xff1a1a2e));

    auto bounds = getLocalBounds();
    int  rollW  = bounds.getWidth()  - kPianoKeyWidth;
    int  rollH  = bounds.getHeight() - kHeaderHeight - 12; // 12 = scrollbar

    // ── Beat grid ─────────────────────────────────────────────────────────────
    g.setColour(juce::Colour(0xff2a2a4e));
    int totalBeats = clip_ ? static_cast<int>(clip_->notes.empty() ? 32 :
        std::ceil(std::max_element(clip_->notes.begin(), clip_->notes.end(),
            [](auto& a, auto& b){ return (a.startBeat + a.durationBeats) < (b.startBeat + b.durationBeats); })
            ->startBeat + std::max_element(clip_->notes.begin(), clip_->notes.end(),
                [](auto& a, auto& b){ return a.durationBeats < b.durationBeats; })->durationBeats)) : 32;

    for (int beat = 0; beat < totalBeats + 1; ++beat) {
        int x = kPianoKeyWidth + beatToX(static_cast<float>(beat));
        bool isBarLine = (beat % beatsPerBar_) == 0;
        g.setColour(isBarLine ? juce::Colour(0xff3a3a6e) : juce::Colour(0xff252540));
        g.drawVerticalLine(x, static_cast<float>(kHeaderHeight), static_cast<float>(rollH + kHeaderHeight));
    }

    // ── Pitch grid ────────────────────────────────────────────────────────────
    for (int pitch = kMidiPitchMin; pitch <= kMidiPitchMax; ++pitch) {
        int y = kHeaderHeight + pitchToY(pitch);
        if (y < kHeaderHeight || y > rollH + kHeaderHeight) continue;
        bool isBlack = juce::MidiMessage::isMidiNoteBlack(pitch);
        g.setColour(isBlack ? juce::Colour(0xff141420) : juce::Colour(0xff1e1e30));
        g.fillRect(kPianoKeyWidth, y, rollW, noteHeight_);
        g.setColour(juce::Colour(0xff252540));
        g.drawHorizontalLine(y + noteHeight_, static_cast<float>(kPianoKeyWidth), static_cast<float>(bounds.getWidth()));
    }

    // ── Piano keys ────────────────────────────────────────────────────────────
    for (int pitch = kMidiPitchMin; pitch <= kMidiPitchMax; ++pitch) {
        int y = kHeaderHeight + pitchToY(pitch);
        if (y < kHeaderHeight || y > rollH + kHeaderHeight) continue;
        bool isBlack = juce::MidiMessage::isMidiNoteBlack(pitch);
        g.setColour(isBlack ? juce::Colours::black : juce::Colours::white);
        g.fillRect(0, y, kPianoKeyWidth - 2, noteHeight_ - 1);
    }

    // ── Notes ────────────────────────────────────────────────────────────────
    if (clip_) {
        for (auto& note : clip_->notes) {
            int x = kPianoKeyWidth + beatToX(note.startBeat);
            int y = kHeaderHeight + pitchToY(note.pitch);
            int w = std::max(2, static_cast<int>(note.durationBeats * pixelsPerBeat_) - 2);
            int h = noteHeight_ - 2;

            float velFactor = static_cast<float>(note.velocity) / 127.0f;
            g.setColour(juce::Colour::fromHSV(0.6f, 0.7f, 0.4f + 0.6f * velFactor, 1.0f));
            g.fillRoundedRectangle(static_cast<float>(x), static_cast<float>(y),
                                   static_cast<float>(w), static_cast<float>(h), 2.0f);
            g.setColour(juce::Colours::white.withAlpha(0.3f));
            g.drawRoundedRectangle(static_cast<float>(x), static_cast<float>(y),
                                   static_cast<float>(w), static_cast<float>(h), 2.0f, 1.0f);
        }
    }

    // ── Playhead ─────────────────────────────────────────────────────────────
    int phX = kPianoKeyWidth + beatToX(static_cast<float>(playheadBeat_));
    if (phX >= kPianoKeyWidth && phX < bounds.getWidth()) {
        g.setColour(juce::Colours::red);
        g.drawVerticalLine(phX, 0.0f, static_cast<float>(bounds.getHeight()));
    }
}

void PianoRollWindow::setClip(const MidiClip* clip, int beatsPerBar)
{
    clip_       = clip;
    beatsPerBar_= beatsPerBar;
    repaint();
}

void PianoRollWindow::setPlayheadBeat(double beat)
{
    playheadBeat_ = beat;

    if (followPlayhead_) {
        float beatF = static_cast<float>(beat);
        float visibleBeats = (getWidth() - kPianoKeyWidth) / pixelsPerBeat_;
        if (beatF > scrollOffsetBeats_ + visibleBeats * 0.8f)
            scrollOffsetBeats_ = beatF - visibleBeats * 0.2f;
        else if (beatF < scrollOffsetBeats_)
            scrollOffsetBeats_ = std::max(0.0f, beatF - 4.0f);
    }

    repaint();
}

void PianoRollWindow::mouseDown(const juce::MouseEvent& e)
{
    juce::ignoreUnused(e);
    // TODO: note creation / selection
}

void PianoRollWindow::mouseDrag(const juce::MouseEvent& e)
{
    juce::ignoreUnused(e);
    // TODO: note drag / resize
}

void PianoRollWindow::mouseUp(const juce::MouseEvent& e)
{
    juce::ignoreUnused(e);
    // TODO: commit note edit to SongDocument
}

void PianoRollWindow::scrollBarMoved(juce::ScrollBar* /*sb*/, double newValue)
{
    scrollOffsetBeats_ = static_cast<float>(newValue);
    repaint();
}

int PianoRollWindow::beatToX(float beat) const noexcept
{
    return static_cast<int>((beat - scrollOffsetBeats_) * pixelsPerBeat_);
}

int PianoRollWindow::pitchToY(int pitch) const noexcept
{
    return (kMidiPitchMax - pitch) * noteHeight_;
}

float PianoRollWindow::xToBeat(int x) const noexcept
{
    return (static_cast<float>(x - kPianoKeyWidth) / pixelsPerBeat_) + scrollOffsetBeats_;
}

int PianoRollWindow::yToPitch(int y) const noexcept
{
    return kMidiPitchMax - ((y - kHeaderHeight) / noteHeight_);
}

} // namespace aria
