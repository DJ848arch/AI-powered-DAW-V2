#include "InstrumentRegistry.h"

namespace aria {

InstrumentRegistry& InstrumentRegistry::instance()
{
    static InstrumentRegistry reg;
    return reg;
}

InstrumentRegistry::InstrumentRegistry()
{
    // General MIDI instrument mapping
    // Format: {canonicalName, gmProgram (0-based), defaultChannel, displayName, family}
    instruments_ = {
        {"drums",          0,   9,  "Drum Kit",          "drums"},    // channel 9, program ignored
        {"bass",           32,  1,  "Acoustic Bass",      "bass"},
        {"electric_bass",  33,  1,  "Electric Bass (finger)", "bass"},
        {"piano",          0,   0,  "Acoustic Grand Piano","keyboard"},
        {"electric_piano", 4,   2,  "Rhodes Electric Piano","keyboard"},
        {"organ",          16,  3,  "Hammond Organ",      "keyboard"},
        {"guitar",         25,  4,  "Acoustic Guitar",    "guitar"},
        {"electric_guitar",29,  4,  "Electric Guitar (muted)","guitar"},
        {"strings",        48,  5,  "String Ensemble",    "strings"},
        {"pad",            88,  6,  "Pad 1 (new age)",    "synth"},
        {"lead_synth",     80,  7,  "Lead 1 (square)",    "synth"},
        {"brass",          61,  8,  "Brass Section",      "brass"},
        {"woodwind",       73, 10,  "Flute",              "woodwind"},
        {"vibraphone",     11, 11,  "Vibraphone",         "mallet"},
        {"marimba",        12, 12,  "Marimba",            "mallet"},
        {"harp",           46, 13,  "Orchestral Harp",    "strings"},
        {"choir",          52, 14,  "Choir Aahs",         "vocal"},
        {"fx",             96, 15,  "FX 1 (rain)",        "fx"},
    };

    for (auto& info : instruments_)
        byName_[info.canonicalName.toStdString()] = info;
}

std::optional<InstrumentInfo> InstrumentRegistry::find(const juce::String& name) const
{
    auto it = byName_.find(name.toStdString());
    if (it == byName_.end()) return std::nullopt;
    return it->second;
}

const std::vector<InstrumentInfo>& InstrumentRegistry::all() const noexcept
{
    return instruments_;
}

juce::String InstrumentRegistry::canonicalFromProgram(int gmProgram) const
{
    for (auto& info : instruments_)
        if (info.gmProgram == gmProgram)
            return info.canonicalName;
    return "piano";
}

} // namespace aria
