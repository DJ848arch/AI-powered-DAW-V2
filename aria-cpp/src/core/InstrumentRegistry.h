#pragma once

#include <juce_core/juce_core.h>
#include <unordered_map>
#include <optional>

namespace aria {

struct InstrumentInfo {
    juce::String canonicalName;  // e.g. "piano"
    int          gmProgram;      // 0-based GM program number
    int          defaultChannel; // preferred MIDI channel (0-15; 9 = drums)
    juce::String displayName;    // "Grand Piano"
    juce::String family;         // "keyboard", "bass", "drums", "strings", etc.
};

// ─────────────────────────────────────────────────────────────────────────────
//  InstrumentRegistry — maps canonical instrument names → GM program numbers
// ─────────────────────────────────────────────────────────────────────────────

class InstrumentRegistry {
public:
    /** Singleton access. */
    static InstrumentRegistry& instance();

    /** Look up by canonical name. Returns nullopt if not found. */
    std::optional<InstrumentInfo> find(const juce::String& canonicalName) const;

    /** All registered instruments. */
    const std::vector<InstrumentInfo>& all() const noexcept;

    /** GM program → canonical name (reverse lookup). */
    juce::String canonicalFromProgram(int gmProgram) const;

private:
    InstrumentRegistry();
    std::vector<InstrumentInfo>                      instruments_;
    std::unordered_map<std::string, InstrumentInfo>  byName_;
};

} // namespace aria
