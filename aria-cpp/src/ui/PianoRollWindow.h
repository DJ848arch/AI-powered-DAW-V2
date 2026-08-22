#pragma once
#include "core/SongDocument.h"
#include <juce_gui_basics/juce_gui_basics.h>

namespace aria {

// ─────────────────────────────────────────────────────────────────────────────
//  PianoRollWindow — shows one track's MIDI notes as a grid
// ─────────────────────────────────────────────────────────────────────────────

class PianoRollWindow : public juce::Component,
                        public juce::ScrollBar::Listener
{
public:
    PianoRollWindow();
    ~PianoRollWindow() override = default;

    void resized() override;
    void paint(juce::Graphics& g) override;
    void mouseDown(const juce::MouseEvent& e) override;
    void mouseDrag(const juce::MouseEvent& e) override;
    void mouseUp  (const juce::MouseEvent& e) override;

    /** Load a clip to display/edit. */
    void setClip(const MidiClip* clip, int beatsPerBar);

    /** Set current playhead position in beats (called ~50ms). */
    void setPlayheadBeat(double beat);

    /** Enable/disable follow-playhead auto-scroll. */
    void setFollowPlayhead(bool follow) { followPlayhead_ = follow; }

    void scrollBarMoved(juce::ScrollBar* sb, double newValue) override;

private:
    int   beatToX(float beat)  const noexcept;
    int   pitchToY(int pitch)  const noexcept;
    float xToBeat(int x)       const noexcept;
    int   yToPitch(int y)      const noexcept;

    const MidiClip*     clip_          = nullptr;
    int                 beatsPerBar_   = 4;
    float               pixelsPerBeat_ = 40.0f;
    int                 noteHeight_    = 8;
    double              playheadBeat_  = 0.0;
    bool                followPlayhead_= true;

    juce::ScrollBar     hScrollBar_ { false };
    float               scrollOffsetBeats_ = 0.0f;

    // Editing state
    std::optional<NoteEvent> draggingNote_;
    juce::Point<int>         dragStart_;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(PianoRollWindow)
};

} // namespace aria
