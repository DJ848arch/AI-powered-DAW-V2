#include "MixerPanel.h"

namespace aria {

// ─────────────────────────────────────────────────────────────────────────────
//  MixerChannelStrip
// ─────────────────────────────────────────────────────────────────────────────

MixerChannelStrip::MixerChannelStrip(const juce::String& name, int ch)
    : trackName(name), midiChannel(ch)
{
    nameLabel_.setText(name, juce::dontSendNotification);
    nameLabel_.setFont(juce::Font(11.0f));
    nameLabel_.setJustificationType(juce::Justification::centred);
    addAndMakeVisible(nameLabel_);

    volumeFader_.setRange(0.0, 1.0);
    volumeFader_.setValue(0.8);
    volumeFader_.onValueChange = [this]{ if (onVolumeChanged) onVolumeChanged(static_cast<float>(volumeFader_.getValue())); };
    addAndMakeVisible(volumeFader_);

    panKnob_.setRange(-1.0, 1.0);
    panKnob_.setValue(0.0);
    panKnob_.onValueChange = [this]{ if (onPanChanged) onPanChanged(static_cast<float>(panKnob_.getValue())); };
    addAndMakeVisible(panKnob_);

    startTimerHz(25); // 25 Hz meter decay
}

void MixerChannelStrip::resized()
{
    auto area = getLocalBounds().reduced(2);
    nameLabel_.setBounds(area.removeFromBottom(16));
    panKnob_.setBounds(area.removeFromBottom(32));
    volumeFader_.setBounds(area);
}

void MixerChannelStrip::paint(juce::Graphics& g)
{
    g.fillAll(juce::Colour(0xff1e1e2e));

    // Level meter (left side, 8px wide)
    auto bounds = getLocalBounds();
    int  meterH = bounds.getHeight() - 16 - 32; // leave room for label and pan
    int  meterY = bounds.getY();

    g.setColour(juce::Colour(0xff0a0a1a));
    g.fillRect(bounds.getX(), meterY, 8, meterH);

    float level = std::min(1.0f, decayLevel_);
    int   filled = static_cast<int>(level * meterH);
    g.setColour(level > 0.8f ? juce::Colours::red
                              : level > 0.5f ? juce::Colours::yellow
                                             : juce::Colour(0xff00cc66));
    g.fillRect(bounds.getX(), meterY + meterH - filled, 8, filled);

    // Border
    g.setColour(juce::Colour(0xff333355));
    g.drawRect(getLocalBounds(), 1);
}

void MixerChannelStrip::notePlaying(int velocity)
{
    peakLevel_  = static_cast<float>(velocity) / 127.0f;
    decayLevel_ = peakLevel_;
    repaint();
}

void MixerChannelStrip::noteStopped()
{
    // Let it decay naturally via timer
}

void MixerChannelStrip::timerCallback()
{
    if (decayLevel_ > 0.0f) {
        decayLevel_ = std::max(0.0f, decayLevel_ - 0.06f);
        repaint();
    }
}

// ─────────────────────────────────────────────────────────────────────────────
//  MixerPanel
// ─────────────────────────────────────────────────────────────────────────────

MixerPanel::MixerPanel()
{
    setOpaque(true);
}

void MixerPanel::resized()
{
    if (strips_.empty()) return;
    int stripW = getWidth() / static_cast<int>(strips_.size());
    for (int i = 0; i < (int)strips_.size(); ++i)
        strips_[static_cast<size_t>(i)]->setBounds(i * stripW, 0, stripW, getHeight());
}

void MixerPanel::paint(juce::Graphics& g)
{
    g.fillAll(juce::Colour(0xff151525));
    if (strips_.empty()) {
        g.setColour(juce::Colours::grey);
        g.drawText("No tracks", getLocalBounds(), juce::Justification::centred);
    }
}

void MixerPanel::setSong(const SongDocument& doc)
{
    strips_.clear();
    for (auto& track : doc.tracks()) {
        auto strip = std::make_unique<MixerChannelStrip>(track.name, track.midiChannel);
        addAndMakeVisible(*strip);
        strips_.push_back(std::move(strip));
    }
    resized();
}

void MixerPanel::onNotePlaying(int midiChannel, int velocity)
{
    for (auto& s : strips_)
        if (s->midiChannel == midiChannel)
            s->notePlaying(velocity);
}

void MixerPanel::onNoteStopped(int midiChannel)
{
    for (auto& s : strips_)
        if (s->midiChannel == midiChannel)
            s->noteStopped();
}

} // namespace aria
