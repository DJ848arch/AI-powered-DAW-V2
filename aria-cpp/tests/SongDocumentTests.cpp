#include <catch2/catch_test_macros.hpp>
#include "core/SongDocument.h"
#include <nlohmann/json.hpp>

using namespace aria;
using json = nlohmann::json;

TEST_CASE("SongDocument empty constructor", "[SongDocument]")
{
    auto doc = SongDocument::empty();
    REQUIRE(doc.documentId().isNotEmpty());
    REQUIRE(doc.tracks().empty());
    REQUIRE(doc.metadata().bpm == Approx(120.0f));
    REQUIRE(doc.metadata().bars == 8);
}

TEST_CASE("SongDocument addTrack and findTrack", "[SongDocument]")
{
    auto doc = SongDocument::empty();

    Track t;
    t.name       = "drums";
    t.instrument = "drums";
    t.midiChannel= 9;

    int idx = doc.addTrack(t);
    REQUIRE(idx == 0);
    REQUIRE(doc.tracks().size() == 1);
    REQUIRE(doc.tracks()[0].id.isNotEmpty());

    auto id = doc.tracks()[0].id;
    auto* found = doc.findTrack(id);
    REQUIRE(found != nullptr);
    REQUIRE(found->name == "drums");

    REQUIRE(doc.findTrack("nonexistent") == nullptr);
}

TEST_CASE("SongDocument clone independence", "[SongDocument]")
{
    auto doc = SongDocument::empty();
    Track t;
    t.name = "bass";
    t.instrument = "bass";
    doc.addTrack(t);

    auto clone = doc.clone();
    REQUIRE(clone.tracks().size() == 1);

    // Mutate clone — original must be unaffected
    clone.mutableTracks()[0].name = "modified";
    REQUIRE(doc.tracks()[0].name == "bass");
    REQUIRE(clone.tracks()[0].name == "modified");
}

TEST_CASE("SongDocument JSON round-trip", "[SongDocument]")
{
    auto doc = SongDocument::empty();
    doc.mutableMetadata().title = "Test Song";
    doc.mutableMetadata().bpm   = 90.0f;
    doc.mutableMetadata().key   = "A minor";
    doc.mutableMetadata().bars  = 4;

    Track t;
    t.name       = "piano";
    t.instrument = "piano";
    t.midiChannel= 0;

    MidiClip clip;
    clip.id       = SongDocument::newUUID();
    clip.startBar = 0;

    NoteEvent note;
    note.pitch         = 60;
    note.startBeat     = 0.0f;
    note.durationBeats = 1.0f;
    note.velocity      = 80;
    clip.notes.push_back(note);
    t.clips.push_back(clip);
    doc.addTrack(t);

    // Serialise
    auto j = doc.toJson();
    REQUIRE(j["metadata"]["title"] == "Test Song");
    REQUIRE(j["metadata"]["bpm"] == Approx(90.0f));
    REQUIRE(j["tracks"].size() == 1);
    REQUIRE(j["tracks"][0]["clips"][0]["notes"][0]["pitch"] == 60);

    // Deserialise into new doc
    SongDocument doc2;
    auto err = doc2.fromJson(j);
    REQUIRE(err.isEmpty());
    REQUIRE(doc2.metadata().title == "Test Song");
    REQUIRE(doc2.metadata().bpm == Approx(90.0f));
    REQUIRE(doc2.tracks().size() == 1);
    REQUIRE(doc2.tracks()[0].clips[0].notes[0].pitch == 60);
}

TEST_CASE("SongDocument removeTrack", "[SongDocument]")
{
    auto doc = SongDocument::empty();
    Track t; t.name = "guitar"; t.instrument = "guitar";
    doc.addTrack(t);
    auto id = doc.tracks()[0].id;

    REQUIRE(doc.removeTrack(id));
    REQUIRE(doc.tracks().empty());
    REQUIRE(!doc.removeTrack(id)); // second remove returns false
}

TEST_CASE("SongDocument totalDurationBeats", "[SongDocument]")
{
    auto doc = SongDocument::empty();
    doc.mutableMetadata().timeSignature.numerator = 4;

    Track t;
    t.name = "bass";
    t.instrument = "bass";
    MidiClip c;
    c.id = SongDocument::newUUID();
    c.startBar = 2;  // bar 2 = beat offset 8
    NoteEvent n; n.pitch = 45; n.startBeat = 2.0f; n.durationBeats = 2.0f; n.velocity = 80;
    c.notes.push_back(n);
    t.clips.push_back(c);
    doc.addTrack(t);

    // startBar=2 → offset=8 beats, note starts at 2.0, dur=2.0 → end=12.0
    float dur = doc.totalDurationBeats();
    REQUIRE(dur == Approx(12.0f));
}

TEST_CASE("AtomicSongDoc thread safety smoke test", "[SongDocument]")
{
    AtomicSongDoc asd;

    // Initial doc
    auto d1 = asd.load();
    REQUIRE(d1 != nullptr);

    // Replace doc
    auto newDoc = std::make_shared<SongDocument>(SongDocument::empty());
    newDoc->mutableMetadata().bpm = 140.0f;
    asd.store(newDoc);

    auto d2 = asd.load();
    REQUIRE(d2->metadata().bpm == Approx(140.0f));
}
