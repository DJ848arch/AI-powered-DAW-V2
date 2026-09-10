# ARIA `.daw` schema

Authoritative in-memory + on-disk shape for the running Python DAW.
Engine is authoritative for **signal flow**. `ProjectManager` is the
adapter that persists and restores the graph. UI widgets are views.

This is the M2 first slice (schema audit + load/save + round-trip).
It does **not** start real insert DSP, real send audio changes, bus
mixer DSP, or metering. C++ `SongDocument` stays a separate format.

**Current version:** `1.1` (additive bump from M1 `1.0`).

---

## Audit (what existed at M1 / `49cb12a`)

| Surface | Tracks / IDs | Buses | Routing | Sends / inserts | Session |
|---------|--------------|-------|---------|-----------------|---------|
| `ProjectManager.new_project` | top-level `tracks: {}` (flat `new_track` records) + `timeline.tracks` | `buses: []` | `track_outputs: {}` | none | `version 1.0`, name, timestamps, `clips`, `midi_clips`, `transport`, `settings` |
| `MainWindow._get_project_data` | `tracks` = TrackPanel envelope `{tracks, next_track_id}` | omitted (engine overlay on save) | omitted (engine overlay) | omitted | `version 1.0`, timeline, transport only |
| `AudioEngine` | int `track_id`; live = buffers/clips or vol/pan/mute/solo | `._buses` (`list_buses`) | `track_outputs` (`get_state`) | `track_sends` / `track_send_levels` in memory only; inserts = identity + test hook | `get_state` has mixer + outputs, **not** buses/sends |
| TrackPanel | int widget ids; `get_state` uses `soloed` (not `solo`) | dest combo via `list_buses` | dest combo → `set_track_output` | no send UI | mixer strip only |
| `new_track()` helper | `{id, name, instrument, clips, muted, solo}` | — | — | — | used by MIDI/agent tests, not File>Save |
| Effects rack | — | — | — | test inserts in `_TEST_INSERTS`; UI placeholder not in `.daw` | — |
| C++ `SongDocument` | MIDI document, `schemaVersion 1.0.0` | — | — | — | **out of scope — do not unify** |

M1 persist contract: `.daw` wrote `track_outputs` + `buses` (schema still `1.0`, missing key = master / no buses). Sends, send levels, and inserts were session-only.

### Known forks (documented, not rewritten this slice)

- **Two `tracks` shapes.** File>Save writes the TrackPanel envelope. `new_project` / `new_track` use a flat id→record map. Load accepts both. Unifying TrackPanel `set_state` (it reassigns ids via `add_track`) would touch dest-picker identity — later slice.
- **`solo` vs `soloed`.** `new_track` uses `solo`; TrackPanel persists `soloed`. Both mean the same strip flag. Engine: `track_solos`.
- **`engine.get_state()` still omits buses/sends/inserts.** M1 tests lock that. Core collects via `list_buses` / `track_sends` / `get_send_level`. Do not add an engine persist API this slice.
- **Inserts are identity slots.** `set_test_insert` is test-only and is **not** written to disk.

---

## Authoritative document (`version: "1.1"`)

JSON object. Unknown keys are kept. Missing graph keys default as M1 did.

```
{
  "version": "1.1",
  "name": str,
  "created_at": iso-8601,
  "modified_at": iso-8601,
  "timeline": { "tracks": {}, "clips": {}, "zoom_level": 1.0, "bpm": 120 },
  "transport": { "bpm", "beats_per_bar", "beat_unit", "metronome_active", "position" },
  "tracks": {},
  "clips": {},
  "midi_clips": {},
  "track_outputs": { "<track_id>": <dest> },
  "buses": ["drum", "fx"],
  "track_sends": { "<track_id>": [<dest>, ...] },
  "track_send_levels": { "<track_id>": { "<dest>": 1.0 } },
  "inserts": { "<track_id>": [ <slot>, ... ] },
  "settings": { "sample_rate": 44100, "bit_depth": 16, "channels": 2 }
}
```

### IDs

- Track ids are integers in the engine and in dest values.
- On disk, map keys are strings (`"0"`). Dest that is a track stays an int; dest that is a bus is a non-empty name ≠ `"master"`.

### Routing (engine graph, project-level — not nested on track records)

| Key | Shape | Missing / empty |
|-----|--------|-----------------|
| `track_outputs` | `{str id: int track \| bus name}` | master (omit master dests) |
| `buses` | sorted unique names, never `"master"` | no buses |
| `track_sends` | `{str id: [dest, ...]}` extra dests; dest cannot be master | no sends |
| `track_send_levels` | `{str id: {str dest: finite ≥ 0 gain}}` | 1.0 if send exists |
| `inserts` | `{str id: [dict slots]}` empty list = identity / dry | no inserts |

Restore order: **buses → track_outputs → clips/live tracks → sends**. Invalid dests are skipped (same as M1). Cycles and unknown dests stay rejected by the engine setter / `validate_graph`.

### Track records

Identity + strip only. Routing is **not** duplicated here.

- Helper `new_track`: `{id, name, instrument, clips, muted, solo}` (unchanged).
- File>Save TrackPanel envelope: `{tracks: {id: {name, volume, pan, muted, soloed}}, next_track_id}`.

`instrument` remains additive (`ensure_track_instrument`). Do not invent output/sends on the track dict.

---

## Migration

`ProjectManager.migrate_project` + `canonicalize_project`:

1. Treat missing / `"1.0"` as M1.
2. Bump `version` to `1.1`.
3. Fill missing graph keys with M1-safe empties (`{}` / `[]`).
4. Normalize dests, bus names, send dests/levels, insert slot lists.
5. Do not drop unknown keys. Do not require new keys in `validate_project` (still `version`, `timeline`, `transport`).

A raw M1 `.daw` without `buses` / `track_outputs` / sends still opens: dests master, no buses, no sends.

Save always writes `1.1` with the graph keys present.

---

## Out of scope (this slice)

- FluidSynth, JUCE, OpenJarvis, blank C++ Edit, new AI.
- Unifying Python `.daw` with C++ `SongDocument`.
- Real insert processing, changing send mix math, bus faders, metering.
- Rewriting TrackPanel id restore or engine `get_state`.
