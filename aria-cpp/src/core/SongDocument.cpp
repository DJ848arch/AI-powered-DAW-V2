#include "SongDocument.h"

#include <juce_core/juce_core.h>
#include <nlohmann/json.hpp>
#include <fstream>
#include <stdexcept>

using json = nlohmann::json;

namespace aria {

// ─────────────────────────────────────────────────────────────────────────────
//  Helpers
// ─────────────────────────────────────────────────────────────────────────────

juce::String SongDocument::newUUID()
{
    return juce::Uuid().toString();
}

// ─────────────────────────────────────────────────────────────────────────────
//  SongDocument
// ─────────────────────────────────────────────────────────────────────────────

SongDocument SongDocument::empty()
{
    SongDocument doc;
    doc.documentId_ = newUUID();
    return doc;
}

SongDocument SongDocument::clone() const
{
    // Value type — default copy is correct (all members are value types or
    // std::vector of value types).
    return *this;
}

int SongDocument::addTrack(Track t)
{
    if (t.id.isEmpty())
        t.id = newUUID();
    tracks_.push_back(std::move(t));
    return static_cast<int>(tracks_.size()) - 1;
}

bool SongDocument::removeTrack(const juce::String& trackId)
{
    auto it = std::find_if(tracks_.begin(), tracks_.end(),
        [&](const Track& t){ return t.id == trackId; });
    if (it == tracks_.end()) return false;
    tracks_.erase(it);
    return true;
}

const Track* SongDocument::findTrack(const juce::String& trackId) const
{
    for (auto& t : tracks_)
        if (t.id == trackId) return &t;
    return nullptr;
}

Track* SongDocument::findTrackMutable(const juce::String& trackId)
{
    for (auto& t : tracks_)
        if (t.id == trackId) return &t;
    return nullptr;
}

bool SongDocument::replaceTrack(const Track& updated)
{
    for (auto& t : tracks_) {
        if (t.id == updated.id) {
            t = updated;
            return true;
        }
    }
    return false;
}

float SongDocument::totalDurationBeats() const
{
    float max = 0.0f;
    for (auto& track : tracks_) {
        for (auto& clip : track.clips) {
            float barOffset = static_cast<float>(clip.startBar) * metadata_.timeSignature.numerator;
            for (auto& note : clip.notes) {
                float end = barOffset + note.startBeat + note.durationBeats;
                if (end > max) max = end;
            }
        }
    }
    return max > 0 ? max : static_cast<float>(metadata_.bars * metadata_.timeSignature.numerator);
}

// ─────────────────────────────────────────────────────────────────────────────
//  JSON serialisation
// ─────────────────────────────────────────────────────────────────────────────

static json noteToJson(const NoteEvent& n)
{
    return {
        {"pitch",         n.pitch},
        {"startBeat",     n.startBeat},
        {"durationBeats", n.durationBeats},
        {"velocity",      n.velocity}
    };
}

static NoteEvent noteFromJson(const json& j)
{
    NoteEvent n;
    n.pitch         = j.value("pitch",         60);
    n.startBeat     = j.value("startBeat",     0.0f);
    n.durationBeats = j.value("durationBeats", 1.0f);
    n.velocity      = j.value("velocity",      80);
    return n;
}

static json clipToJson(const MidiClip& c)
{
    json notesArr = json::array();
    for (auto& n : c.notes) notesArr.push_back(noteToJson(n));
    return {
        {"id",       c.id.toStdString()},
        {"startBar", c.startBar},
        {"name",     c.name.toStdString()},
        {"color",    c.color.toStdString()},
        {"notes",    notesArr}
    };
}

static MidiClip clipFromJson(const json& j)
{
    MidiClip c;
    c.id       = juce::String(j.value("id", "").c_str());
    c.startBar = j.value("startBar", 0);
    c.name     = juce::String(j.value("name", "").c_str());
    c.color    = juce::String(j.value("color", "").c_str());
    if (j.contains("notes")) {
        for (auto& nj : j["notes"])
            c.notes.push_back(noteFromJson(nj));
    }
    return c;
}

static json trackToJson(const Track& t)
{
    json clipsArr = json::array();
    for (auto& c : t.clips) clipsArr.push_back(clipToJson(c));

    json pluginsArr = json::array();
    for (auto& p : t.pluginChain)
        pluginsArr.push_back({{"pluginId", p.pluginId.toStdString()},
                              {"enabled",  p.enabled},
                              {"stateB64", p.stateB64.toStdString()}});

    return {
        {"id",          t.id.toStdString()},
        {"name",        t.name.toStdString()},
        {"instrument",  t.instrument.toStdString()},
        {"midiChannel", t.midiChannel},
        {"gmProgram",   t.gmProgram},
        {"volume",      t.volume},
        {"pan",         t.pan},
        {"muted",       t.muted},
        {"solo",        t.solo},
        {"clips",       clipsArr},
        {"pluginChain", pluginsArr}
    };
}

static Track trackFromJson(const json& j)
{
    Track t;
    t.id          = juce::String(j.value("id", "").c_str());
    t.name        = juce::String(j.value("name", "").c_str());
    t.instrument  = juce::String(j.value("instrument", "").c_str());
    t.midiChannel = j.value("midiChannel", 0);
    t.gmProgram   = j.value("gmProgram",   0);
    t.volume      = j.value("volume",      0.8f);
    t.pan         = j.value("pan",         0.0f);
    t.muted       = j.value("muted",       false);
    t.solo        = j.value("solo",        false);
    if (j.contains("clips"))
        for (auto& cj : j["clips"]) t.clips.push_back(clipFromJson(cj));
    if (j.contains("pluginChain")) {
        for (auto& pj : j["pluginChain"]) {
            PluginSlot ps;
            ps.pluginId = juce::String(pj.value("pluginId", "").c_str());
            ps.enabled  = pj.value("enabled", true);
            ps.stateB64 = juce::String(pj.value("stateB64", "").c_str());
            t.pluginChain.push_back(ps);
        }
    }
    return t;
}

json SongDocument::toJson() const
{
    json tracksArr = json::array();
    for (auto& t : tracks_) tracksArr.push_back(trackToJson(t));

    return {
        {"schemaVersion", "1.0.0"},
        {"metadata", {
            {"title",         metadata_.title.toStdString()},
            {"bpm",           metadata_.bpm},
            {"key",           metadata_.key.toStdString()},
            {"timeSignature", {
                {"numerator",   metadata_.timeSignature.numerator},
                {"denominator", metadata_.timeSignature.denominator}
            }},
            {"bars",  metadata_.bars},
            {"genre", metadata_.genre.toStdString()},
            {"vibe",  metadata_.vibe.toStdString()}
        }},
        {"tracks", tracksArr},
        {"loopRegion", {
            {"enabled",  loopRegion_.enabled},
            {"startBar", loopRegion_.startBar},
            {"endBar",   loopRegion_.endBar}
        }}
    };
}

juce::String SongDocument::fromJson(const json& j)
{
    try {
        if (j.contains("metadata")) {
            auto& m = j["metadata"];
            metadata_.title = juce::String(m.value("title", "Untitled").c_str());
            metadata_.bpm   = m.value("bpm",  120.0f);
            metadata_.key   = juce::String(m.value("key", "C major").c_str());
            metadata_.bars  = m.value("bars", 8);
            metadata_.genre = juce::String(m.value("genre", "").c_str());
            metadata_.vibe  = juce::String(m.value("vibe",  "").c_str());
            if (m.contains("timeSignature")) {
                metadata_.timeSignature.numerator   = m["timeSignature"].value("numerator",   4);
                metadata_.timeSignature.denominator = m["timeSignature"].value("denominator", 4);
            }
        }
        tracks_.clear();
        if (j.contains("tracks"))
            for (auto& tj : j["tracks"]) tracks_.push_back(trackFromJson(tj));

        if (j.contains("loopRegion")) {
            loopRegion_.enabled  = j["loopRegion"].value("enabled",  false);
            loopRegion_.startBar = j["loopRegion"].value("startBar", 0);
            loopRegion_.endBar   = j["loopRegion"].value("endBar",   8);
        }
        return {};
    } catch (const std::exception& e) {
        return juce::String("JSON parse error: ") + e.what();
    }
}

juce::String SongDocument::loadFromFile(const juce::File& file)
{
    if (!file.existsAsFile())
        return "File not found: " + file.getFullPathName();
    try {
        json j = json::parse(file.loadFileAsString().toStdString());
        return fromJson(j);
    } catch (const std::exception& e) {
        return juce::String("Failed to load: ") + e.what();
    }
}

juce::String SongDocument::saveToFile(const juce::File& file) const
{
    try {
        auto j = toJson();
        auto text = j.dump(2);
        if (!file.replaceWithText(juce::String(text.c_str())))
            return "Failed to write file: " + file.getFullPathName();
        return {};
    } catch (const std::exception& e) {
        return juce::String("Save failed: ") + e.what();
    }
}

// ─────────────────────────────────────────────────────────────────────────────
//  AtomicSongDoc
// ─────────────────────────────────────────────────────────────────────────────

AtomicSongDoc::AtomicSongDoc()
{
    doc_ = std::make_shared<SongDocument>(SongDocument::empty());
}

std::shared_ptr<const SongDocument> AtomicSongDoc::load() const noexcept
{
    juce::SpinLock::ScopedLockType sl(lock_);
    return doc_;
}

void AtomicSongDoc::store(std::shared_ptr<SongDocument> newDoc) noexcept
{
    juce::SpinLock::ScopedLockType sl(lock_);
    doc_ = std::move(newDoc);
}

SongDocument AtomicSongDoc::cloneCurrent() const
{
    return load()->clone();
}

} // namespace aria
