#pragma once
#include "core/SongDocument.h"
#include <juce_gui_basics/juce_gui_basics.h>
#include <vector>

namespace aria {

// ─────────────────────────────────────────────────────────────────────────────
//  MixerChannelStrip — single channel with fader, pan, and live meter
// ─────────────────────────────────────────────────────────────────────────────

class MixerChannelStrip : public juce::Component, private juce::Timer {
public:
    MixerChannelStrip(const juce::String& trackName, int midiChannel);

    void paint(juce::Graphics& g) override;
    void resized() override;

    void notePlaying(int velocity);
    void noteStopped();

    juce::String trackName;
    int          midiChannel;

    std::function<void(float volume)> onVolumeChanged;
    std::function<void(float pan)>    onPanChanged;

private:
    void timerCallback() override;

    juce::Slider volumeFader_ { juce::Slider::LinearVertical,   juce::Slider::NoTextBox };
    juce::Slider panKnob_     { juce::Slider::RotaryVerticalDrag, juce::Slider::NoTextBox };
    juce::Label  nameLabel_;

    float peakLevel_   = 0.0f;
    float decayLevel_  = 0.0f;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(MixerChannelStrip)
};

// ─────────────────────────────────────────────────────────────────────────────
//  MixerPanel — row of channel strips
// ─────────────────────────────────────────────────────────────────────────────

class MixerPanel : public juce::Component {
public:
    MixerPanel();
    ~MixerPanel() override = default;

    void resized() override;
    void paint(juce::Graphics& g) override;

    /** Rebuild strips from a SongDocument. */
    void setSong(const SongDocument& doc);

    /** Called by AudioEngine when a note starts on a channel. */
    void onNotePlaying(int midiChannel, int velocity);

    /** Called by AudioEngine when a channel goes silent. */
    void onNoteStopped(int midiChannel);

private:
    std::vector<std::unique_ptr<MixerChannelStrip>> strips_;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(MixerPanel)
};

} // namespace aria
