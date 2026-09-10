# ARIA `.daw` schema

Authoritative in-memory + on-disk shape for the running Python DAW.
Engine is authoritative for **signal flow**. `ProjectManager` is the
adapter that persists and restores the graph. UI widgets are views.

**Current version:** `1.1` (additive bump from M1 `1.0`). This batch
adds real insert DSP, pre/post-fader sends, bus mixer channels, and
engine meter *data*. Keys below are additive: missing = M1 defaults.

C++ `SongDocument` stays a separate format.

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

M1 persist contract: `.daw` wrote `track_outputs` + `buses` (schema still `1.0`, missing key = master / no buses). Sends, send levels, and inserts were session-only until the M2 schema slice.

### Known forks (documented, not rewritten this slice)

- **Two `tracks` shapes.** File>Save writes the TrackPanel envelope. `new_project` / `new_track` use a flat id→record map. Load accepts both. Unifying TrackPanel `set_state` (it reassigns ids via `add_track`) would touch dest-picker identity — later slice.
- **`solo` vs `soloed`.** `new_track` uses `solo`; TrackPanel persists `soloed`. Both mean the same strip flag. Engine: `track_solos`.
- **`engine.get_state()` still omits buses/sends/inserts.** M1 tests lock that. Core collects via public engine APIs. Do not stuff graph keys into `get_state`.
- **`set_test_insert` / `_insert_processor` remain M1 test hooks.** They run *after* the persisted insert chain.

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
  "track_send_modes": { "<track_id>": { "<dest>": "pre"|"post" } },
  "inserts": { "<track_id|bus_name>": [ <slot>, ... ] },
  "bus_outputs": { "<bus>": <dest> },
  "bus_volumes": { "<bus>": 0.0..1.0 },
  "bus_pans": { "<bus>": -1.0..1.0 },
  "bus_sends": { "<bus>": [<dest>, ...] },
  "bus_send_levels": { "<bus>": { "<dest>": 1.0 } },
  "bus_send_modes": { "<bus>": { "<dest>": "pre"|"post" } },
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
| `track_send_modes` | `{str id: {str dest: "pre"\|"post"}}` | `"post"` (M1) |
| `inserts` | `{str id or bus name: [dict slots]}` empty list = identity / dry | no inserts |
| `bus_outputs` | `{bus name: int track \| bus name}` | master |
| `bus_volumes` / `bus_pans` | `{bus name: float}` | volume 1.0, pan 0.0 |
| `bus_sends` / `_levels` / `_modes` | same shape as track sends | no bus sends |

Restore order: **buses → bus mixer → track_outputs → inserts → sends**. Invalid dests are skipped (same as M1). Cycles and unknown dests stay rejected by the engine setter / `validate_graph`.

### Insert slots

Built-in processors (not a plugin host):

| `type` | Behavior | Params |
|--------|----------|--------|
| `identity` / `passthru` | no-op | — |
| `gain` | multiply | `gain` (default 1.0) |
| `offset` | add a constant (order-proving stage) | `amount` (default 0.0) |

`enabled: false` bypasses that slot. Unknown types are stored and treated as identity. Empty `[]` is dry. Slots run **in list order**.

### Track records

Identity + strip only. Routing is **not** duplicated here.

- Helper `new_track`: `{id, name, instrument, clips, muted, solo}` (unchanged).
- File>Save TrackPanel envelope: `{tracks: {id: {name, volume, pan, muted, soloed}}, next_track_id}`.

`instrument` remains additive (`ensure_track_instrument`). Do not invent output/sends on the track dict.

---

## Signal flow (engine)

```
clips on track
  → insert chain (empty = dry)
  → pre-fader send tap  (after inserts; ignores volume/pan)
  → mute / solo / volume / pan
  → post-fader send tap (default; M1)
  → main dest: master | track (one-hop into dest before dest fader) | bus

bus input (track mains + sends + upstream buses)
  → insert chain
  → pre-fader bus send
  → bus volume / pan
  → post-fader bus send
  → dest: master (default) | another bus | a track whose dest is master or a bus
```

**Send rule.** A send is EXTRA, not a replacement of the main dest. Level 0
silences only that send. Mute/solo silence both pre and post taps.
`post` (default) follows the source fader — source volume 0 silences a
post send. `pre` does not. Track→track sends are not main-output cycle
edges (M1: `1→0` main plus send `0→1` is allowed). Bus→bus sends that
would cycle the bus graph are rejected. Dest cannot be `"master"` or
self; unknown dests stay `ValueError`.

**Bus dest restriction.** A bus may output to a track only if that
track's dest is master or a bus. Bus→track→track would need a recursive
mix walker beyond M1 one-hop and is rejected.

**Meters.** `AudioEngine.get_meters()` / `get_meter(channel)` expose
peak + RMS for tracks (post-fader channel out), buses (post-fader), and
Master (after the tanh limiter). Engine data only — no mixer UI in this
slice.

---

## Migration

`ProjectManager.migrate_project` + `canonicalize_project`:

1. Treat missing / `"1.0"` as M1.
2. Bump `version` to `1.1`.
3. Fill missing graph keys with M1-safe empties (`{}` / `[]`).
4. Normalize dests, bus names, send dests/levels/modes, insert slot lists, bus mixer.
5. Do not drop unknown keys. Do not require new keys in `validate_project` (still `version`, `timeline`, `transport`).

A raw M1 `.daw` without `buses` / `track_outputs` / sends still opens: dests master, no buses, no sends.

Save always writes `1.1` with the graph keys present.

---

## Out of scope

- FluidSynth, JUCE, OpenJarvis, blank C++ Edit, new AI.
- Unifying Python `.daw` with C++ `SongDocument`.
- Plugin marketplace / VST host.
- Dedicated mixer metering UI (engine meter *data* is in).
- Rewriting TrackPanel id restore or engine `get_state`.
