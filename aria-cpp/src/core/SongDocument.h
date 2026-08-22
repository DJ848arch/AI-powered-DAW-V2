#pragma once

#include <juce_core/juce_core.h>
#include <nlohmann/json.hpp>
#include <atomic>
#include <memory>
#include <string>
#include <vector>

namespace aria {

// ─────────────────────────────────────────────────────────────────────────────
//  Value types (plain structs, trivially copyable or cheaply copied)
// ─────────────────────────────────────────────────────────────────────────────

struct NoteEvent {
    int   pitch         = 60;
    float startBeat     = 0.0f;
    float durationBeats = 1.0f;
    int   velocity      = 80;
};

struct MidiClip {
    juce::String          id;          // UUID
    int                   startBar = 0;
    juce::String          name;
    juce::String          color;       // "#RRGGBB"
    std::vector<NoteEvent> notes;
};

struct PluginSlot {
    juce::String pluginId;
    bool         enabled = true;
    juce::String stateB64;  // base64-encoded plugin state
};

struct Track {
    juce::String             id;           // UUID
    juce::String             name;
    juce::String             instrument;   // "drums", "bass", etc.
    int                      midiChannel = 0;
    int                      gmProgram   = 0;
    float                    volume      = 0.8f;
    float                    pan         = 0.0f;
    bool                     muted       = false;
    bool                     solo        = false;
    std::vector<MidiClip>    clips;
    std::vector<PluginSlot>  pluginChain;
};

struct TimeSignature {
    int numerator   = 4;
    int denominator = 4;
};

struct SongMetadata {
    juce::String  title         = "Untitled";
    float         bpm           = 120.0f;
    juce::String  key           = "C major";
    TimeSignature timeSignature;
    int           bars          = 8;
    juce::String  genre;
    juce::String  vibe;
};

struct LoopRegion {
    bool enabled  = false;
    int  startBar = 0;
    int  endBar   = 8;
};

// ─────────────────────────────────────────────────────────────────────────────
//  SongDocument — immutable value type
//
//  Rule: never mutate in place. Copy, modify the copy, then atomically swap.
//  The audio thread reads via std::atomic<std::shared_ptr<SongDocument>>.
// ─────────────────────────────────────────────────────────────────────────────

class SongDocument {
public:
    SongDocument() = default;

    // Named constructor — create an empty document with a UUID
    static SongDocument empty();

    // Deep copy (use before mutation)
    SongDocument clone() const;

    // ── Serialisation ────────────────────────────────────────────────────────

    /** Serialise to nlohmann JSON. Throws on error. */
    nlohmann::json toJson() const;

    /** Deserialise from nlohmann JSON. Returns error string or "" on success. */
    juce::String fromJson(const nlohmann::json& j);

    /** Convenience: load from file path. Returns error string or "" on success. */
    juce::String loadFromFile(const juce::File& file);

    /** Convenience: save to file. Returns error string or "" on success. */
    juce::String saveToFile(const juce::File& file) const;

    // ── Accessors ────────────────────────────────────────────────────────────

    const SongMetadata&          metadata()    const noexcept { return metadata_; }
    const std::vector<Track>&    tracks()      const noexcept { return tracks_; }
    const LoopRegion&            loopRegion()  const noexcept { return loopRegion_; }
    const juce::String&          documentId()  const noexcept { return documentId_; }

    // ── Mutation helpers (call on a clone()) ─────────────────────────────────

    SongMetadata&       mutableMetadata()   noexcept { return metadata_; }
    std::vector<Track>& mutableTracks()     noexcept { return tracks_; }
    LoopRegion&         mutableLoopRegion() noexcept { return loopRegion_; }

    /** Add a track and return its index. */
    int  addTrack(Track t);

    /** Remove track by id. Returns true if found. */
    bool removeTrack(const juce::String& trackId);

    /** Find track by id. Returns nullptr if not found. */
    const Track* findTrack(const juce::String& trackId) const;
    Track*       findTrackMutable(const juce::String& trackId);

    /** Replace a track (must have same id). Returns true if found. */
    bool replaceTrack(const Track& updated);

    // ── Utility ──────────────────────────────────────────────────────────────

    /** Total duration in beats (max end beat across all clips). */
    float totalDurationBeats() const;

    /** Generate a new UUID string. */
    static juce::String newUUID();

private:
    juce::String       documentId_;
    SongMetadata       metadata_;
    std::vector<Track> tracks_;
    LoopRegion         loopRegion_;
};

// ─────────────────────────────────────────────────────────────────────────────
//  AtomicSongDoc — thread-safe shared_ptr swap for audio thread
// ─────────────────────────────────────────────────────────────────────────────

class AtomicSongDoc {
public:
    AtomicSongDoc();

    /** Audio thread: read current doc. Lock-free. */
    std::shared_ptr<const SongDocument> load() const noexcept;

    /** Agent / UI thread: replace doc atomically. */
    void store(std::shared_ptr<SongDocument> newDoc) noexcept;

    /** Helper: clone current doc, return modifiable copy. */
    SongDocument cloneCurrent() const;

private:
    // std::atomic<std::shared_ptr<>> requires C++20 and a lock-free
    // specialisation. We use a juce::SpinLock as a fallback that's
    // still safe for the RT thread (spin is brief — just a pointer swap).
    mutable juce::SpinLock              lock_;
    std::shared_ptr<const SongDocument> doc_;
};

} // namespace aria
