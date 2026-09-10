# AI-Powered DAW roadmap

Source of truth: local `/workspace/aria`.
ClickUp = plan (workspace `90141241740`, Team Space `90145572472`, existing ARIA list `901419614214`).
Notion = development journal.
Google Calendar = daily increment (America/Boise, availability FREE).

**CURRENTLY APPROVED:** Milestone 1 Routing only.

**NOT APPROVED** (planning items only, do not execute): FluidSynth, unifying `.daw` vs C++ `SongDocument`, GitHub catch-up, blank C++ Edit, OpenJarvis, JUCE, new AI systems/roles.

Two project formats exist (**document, do not unify** unless Daniel explicitly approves):

| Format | Location | Schema | Role today |
|--------|----------|--------|------------|
| Python `.daw` | `src/project.py` | `version: "1.0"` | Running UI/session format. JSON. Tracks, clips, `midi_clips`, timeline, transport, crash-safe atomic save. |
| C++ `SongDocument` | `aria-cpp/resources/schemas/song_schema.json` | `schemaVersion: "1.0.0"` | MIDI-only document for the JUCE/Tracktion target. Separate from `.daw`. JUCE on hold. |

GitHub `https://github.com/DJ848arch/AI-powered-DAW-V2` `main` is behind (Aug 22 playback slice only). Do not clone. Do not push. Do not catch up unless Daniel approves.

ClickUp import landed 2026-08-28: folder **AI-Powered DAW** `901412060516`, list **M1 Routing — APPROVED** `901419670127`, list **Roadmap — planning only** `901419670128`. Existing ARIA list `901419614214` / task `86bbngfza` remains the approved-goal pointer (retitled). Do not treat future milestones as authorization to execute them.

---

## Systems

ClickUp folder (created 2026-08-28): **AI-Powered DAW** `901412060516` in space `90145572472`.

Lists:

1. **M1 Routing** — APPROVED (daily batches live here until M1 completion review + Daniel’s approval).
2. **Roadmap** — planning only (M2–M20 as milestone tasks, **not** daily batches until approved).

Existing list `901419614214` (ARIA) remains the approved-goal source until the new folder/lists exist. After import, M1 work tasks live in **M1 Routing**; M2–M20 stay in **Roadmap** as planning shells.

Task statuses we will map:

`BACKLOG` / `TODAY` / `IN PROGRESS` / `QA` / `BLOCKED` / `DONE`

Use ClickUp native statuses + tags if custom statuses are unavailable. Suggested mapping if native statuses cannot be customized:

| Desired | ClickUp native (typical) | Tag |
|---------|--------------------------|-----|
| BACKLOG | to do | `BACKLOG` |
| TODAY | to do | `TODAY` |
| IN PROGRESS | in progress | `IN PROGRESS` |
| QA | in progress | `QA` |
| BLOCKED | to do (or blocked if present) | `BLOCKED` |
| DONE | complete | `DONE` |

Also tag: `APPROVED` (executable), `PLANNING-ONLY` (do not execute), `M1`, owner (`Engine` / `Core` / `UI` / `QA` / `Inspector`).

ClickUp hierarchy after import:

```
AI-Powered DAW (folder, space 90145572472)
├── M1 Routing          ← APPROVED list
│   ├── [DONE] slice 1 tasks
│   ├── Daily Batch — 2026-08-27 (3 tasks)
│   └── BACKLOG remaining M1 tasks (no frozen future dates)
└── Roadmap             ← PLANNING ONLY list
    ├── M2 … M20 milestone tasks (shells, not daily batches)
    └── (daily batches created only after Daniel approves that milestone)
```

Notion journal required sections (one child page per weekday increment): TODAY'S GOALS, COMPLETED, WHAT IS WORKING NOW, TEST / QA RESULTS, WHAT WAS SUCCESSFUL, WHAT DID NOT WORK, PROBLEMS DISCOVERED, DECISIONS MADE, ARCHITECTURE / IMPLEMENTATION NOTES, FILES OR SYSTEMS CHANGED, WHAT REMAINS IN THIS MILESTONE, BLOCKERS, RECOMMENDED NEXT THREE TASKS, CONTEXT FOR TOMORROW.

Calendar event title: `AI DAW — [Milestone] — Daily Increment`. Timezone America/Boise, availability FREE. Append `OUTCOME` on the **same** event; do not create a disconnected duplicate.

---

## Current state (2026-08-28 kickoff)

Local `/workspace/aria` is the working DAW. Python/PyQt6 shell, Play, MIDI piano roll, AgentManager apply, crash-safe save.

Routing **DONE locally** through 2026-08-27 (independent QA):

- Slice 1: `set_track_output` / `get_track_output` in `src/audio_engine.py`; dest fader; WAV+MIDI follow dest; unknown dest and self-output rejected; default mix unchanged
- Persist + restore `track_outputs` in `.daw` (schema still 1.0, additive; missing key = master). File>Save/Open/autosave pass `engine=`
- Multi-track cycle detection in the setter (`_would_create_output_cycle`). `tests/test_audio_engine_cycles.py` + routing
- 26 related tests green (track_outputs, project, routing, cycles). Full suite last recorded by UI as 75; do not re-invent. ~58 were green before routing work.

**Not on GitHub.** GitHub `main` is the Aug 22 playback slice (`fac1938`) only. OAuth GitHub plugin `needsAuth`; PAT MCP connected. Do not push.

**TODAY 2026-08-28 batch** (green-lit by Daniel; IN PROGRESS at kickoff):

1. Graph validation — Engine — ClickUp `86bbpakz5`
2. Destination UI picker — UI — ClickUp `86bbpam0p` (no buses in dropdown)
3. Buses (model + mix path) — Engine — ClickUp `86bbpam4d` (persist later; no sends)

Still missing after today (unless they finish): bus persist (Core), sends, send levels, inserts/routing integration, expanded tests, regression, milestone completion review.

Roster seated for executable work: Inspector (read-only map), Core (project state / `.daw`), Engine (audio / MIDI / mixer / routing), UI (PyQt), QA (tests / independent verification). JUCE and new AI roles remain on hold.

---

## Milestone 1 — Routing Core (APPROVED)

**Status:** Completion report submitted 2026-09-02. Awaiting Daniel’s approval. **STOP. Do not start M2.** Still the only approved milestone until he says otherwise.
**ClickUp:** list **M1 Routing**. Existing task id `86bbngfza` is the approved routing goal (retitle on import if still generic).

### Objective

Complete reliable internal signal routing in the running Python engine and persist it in `.daw` project files. Do not broaden into unrelated features (no FluidSynth, no format unify, no GitHub catch-up, no C++/JUCE, no new AI).

### Definition of done

A user (and tests) can rely on internal signal routing:

- Track → Master (default)
- Track → Track
- Persist + restore routes in project files (`.daw`)
- Full cycle detection (not only self-output)
- Invalid route rejection
- Routing graph validation
- Destination selection + routing UI picker
- Bus architecture
- Sends
- Send levels
- Inserts/routing integration where appropriate
- Routing state tests + regression + independent QA

Default mixing behavior remains unchanged for tracks that still output to master.

### Dependencies

- Slice 1 engine routing (DONE locally): `src/audio_engine.py` `set_track_output` / `get_track_output` / `track_outputs` / dest fader / WAV+MIDI follow dest.
- Crash-safe `.daw` save/load already exists in `src/project.py` (schema 1.0). Persist work **adds** `track_outputs`; it does not redesign the schema or unify with C++ `SongDocument`.
- UI picker depends on engine dest API + persist/restore.
- Buses/sends/inserts depend on a validated acyclic graph and persist/restore.
- QA gates every batch. Independent QA required before DONE.

### Owners

| Area | Owner |
|------|--------|
| Routing graph, cycle detection, buses, sends, send levels, mix path | **Engine** |
| Persist/restore `track_outputs` (and later buses/sends) in `.daw`; `get_state`/`set_state` wiring on save/load | **Core** |
| Destination UI picker and routing controls (no new roles) | **UI** |
| Verification, routing tests, regression, independent sign-off | **QA** |
| Read-only map if a batch needs a file/state inventory | **Inspector** |

Engine owns routing. Core owns `.daw` persist/restore. UI owns the picker. QA owns verification.

### Risks

- Saving routes without restore (or restore without save) produces silent session loss.
- Cycle detection that is too shallow (self-only) still allows 0→1→0 and longer loops to hang or blow the mix.
- Graph validation that mutates dests instead of rejecting them hides bugs.
- UI picker shipped before persist/restore will show dests that vanish on reopen.
- Buses/sends/inserts exploding scope before the track-graph is solid.
- Dual formats: do **not** write C++ `SongDocument` routing fields as part of M1.
- GitHub remaining behind: local is source of truth; a push is **not** an M1 task.

### Required tests

Named tests to add or keep (counts only where already known):

- Keep slice 1: `tests/test_audio_engine_routing.py` (5 passed, QA PASS).
- Persist: round-trip `track_outputs` in `.daw`; missing key = master.
- Restore: load restores `0→1` and dest-fader behavior.
- Cycles: `0→1→0` (and longer) raises in the setter; acyclic `0→1` still works; self-output already rejected.
- Graph validation: invalid graph rejected; valid graph accepted.
- Buses/sends/send levels: once implemented, unit + mix-path tests.
- Inserts/routing integration: only where the current architecture supports it.
- Regression: do not invent a suite count. Re-run existing tests; record the number QA actually observes. ~58 were green before routing work; slice 1 added 5.

Implementation is not DONE because code was written. Evidence required: unit/integration tests, regression, and independent QA.

### Completion gate

Do **not** start M2 (or any later milestone) when the backlog looks empty. Run a milestone completion review:

- DoD satisfied (every bullet above).
- Required tests pass; relevant regression passes.
- QA independently confirms the milestone.
- No unresolved blocker compromises routing.
- Notion documents the routing graph, persist keys, and known limitations.
- ClickUp reflects actual state.

Then write a **MILESTONE COMPLETION REPORT** (Milestone / Status / What was built / What now works / Tests / QA / Known limitations / Technical debt / Deferred items / Recommendation for next milestone) and **STOP**. Wait for Daniel’s approval.

### Task inventory

Do **NOT** freeze future daily batches. The morning loop picks 3 from remaining M1 work. Split any task that is too large **before** work starts.

#### DONE (slice 1, 2026-08-27, local only)

- [DONE] Track → master default — Engine — `src/audio_engine.py` — missing dest / `"master"` mixes as today. Tests: default two-tone mix on master (`test_default_two_tones_both_appear_on_master`).
- [DONE] Track → track — Engine — `set_track_output(src, dest_id)` — dest fader applies. Tests: dest volume 0 silences master; dest volume 0.5 scales through fader.
- [DONE] WAV + MIDI follow dest — Engine — mix path — WAV ndarray and `render_midi` buffer on the same source follow dest. Tests: `test_wav_ndarray_and_render_midi_both_follow_dest`.
- [DONE] Unknown dest reject — Engine — setter raises `ValueError` for unknown dest strings. Tests: `test_set_track_output_rejects_unknown_dest`.
- [DONE] Self-output reject — Engine — `set_track_output(0, 0)` raises. Tests: same file.
- [DONE] Slice 1 tests — QA — `tests/test_audio_engine_routing.py` **5 passed**.
- [DONE] QA independent PASS — QA — slice 1 accepted. Not on GitHub.

#### DONE 2026-08-27 batch (independent QA PASS)

1. Persist `track_outputs` in `.daw` — Core — DONE
2. Restore routes on project load — Core — DONE
3. Multi-track cycle detection — Engine — DONE

File>Save/Open/autosave pass `engine=`. Schema still 1.0 additive. ClickUp: Daily Batch — 2026-08-27 `86bbpakq7`.

#### TODAY 2026-08-28 batch (max 3; green-lit; IN PROGRESS at kickoff)

Calendar: `AI DAW — M1 Routing Core — Daily Increment` (America/Boise, FREE) event `70l0hn9hos52di6euroca135ng`. ClickUp parent `86bbpakpu`.

1. **Graph validation**
   - Owner: **Engine**
   - Status: IN PROGRESS
   - ClickUp: `86bbpakz5`
   - Files: `src/audio_engine.py`
   - Objective: Reject invalid graphs (dangling dest, type errors, non-int dest ids, inconsistent `track_outputs` vs live tracks) without mutating dests. Accept valid acyclic graphs.
   - Tests: invalid rejected, valid accepted. Independent QA before DONE.

2. **Destination UI picker**
   - Owner: **UI**
   - Status: IN PROGRESS
   - ClickUp: `86bbpam0p`
   - Files: `src/track_panel.py` (+ `src/main_window.py` if wiring needed)
   - Objective: Dest selector on the track. Master + other tracks. Writes through `set_track_output`. Reflects `get_track_output`. No buses in this first picker.
   - Tests: picker sets dest; unknown/self still rejected by engine. Independent QA before DONE.

3. **Buses (model + mix path)**
   - Owner: **Engine**
   - Status: IN PROGRESS
   - ClickUp: `86bbpam4d`
   - Files: `src/audio_engine.py`
   - Objective: Named buses as routing destinations; tracks may output to a bus; buses output to master. Mix path only. Persist later (Core). No sends today.
   - Tests: unit + mix-path. Independent QA before DONE.

#### BACKLOG (later days, still M1 only — morning loop picks 3)

- Bus persist in `.daw` — Core — after Engine buses mix path lands. Schema stays 1.0 additive if possible.
- Sends — Engine (+ UI later) — per-track send to a bus or dest **in addition to** main output. Split if too large.
- Send levels — Engine — send gain independent of track fader. Tests: send level 0 is silent on the send path; main output unchanged.
- Inserts/routing integration — Engine — where the current Python architecture supports it: inserts stay on the channel and routing still applies to post- or pre-fader as documented. Do not start JUCE plugin hosting. Do not invent a VST host.
- Expanded routing state tests — QA — cover persist keys, cycles, buses, sends, picker→engine, missing-key default.
- Regression — QA — re-run existing tests after routing changes. Record the actual count. ~58 were green before routing work; do not invent a new total.
- Milestone completion review — QA + Inspector (read-only) + Chief of Staff — DoD check, completion report, **stop** for Daniel’s approval.

Import note: create one ClickUp task per bullet above. Put the 2026-08-27 three under a parent “Daily Batch — 2026-08-27”. Do **not** pre-create dated batches for later days.

---

## Milestones 2–20 — PLANNING ONLY

Do not execute. Do not create daily batches until Daniel approves the milestone and M1 (then each predecessor) has a completion report. Seated roles remain Inspector / Core / Engine / UI / QA. JUCE and new AI roles stay on hold. ClickUp: one milestone task per section in list **Roadmap**, tag `PLANNING-ONLY`. Sub-bullets become subtasks on approval, then the morning loop picks 3 from remaining.

---

## Milestone 2 — Project/session reliability

**Status:** PLANNING ONLY.
**Name:** Project/session reliability.

### Objective

Make projects reliably save, load, recover, and reproduce the user’s session in the running Python `.daw` format.

### Definition of done

Open/save/reopen reproduces tracks, clips, MIDI, mixer, timeline, routing (from M1), and supported effect state. Crash recovery and autosave are proven. Missing files, migration, and corruption fail safely. Dual formats remain documented.

### Dependencies

- M1 complete and approved (routing persist/restore is an M1 deliverable; M2 must not regress it).
- Existing crash-safe save in `src/project.py` (atomic `.tmp` + `os.replace` + backup-before-replace + load migrate-then-validate). Schema still Python `1.0`.

### Responsible seated roles

Core (serialization, migration, autosave, corruption handling); Engine (mixer/routing/MIDI state that must round-trip); UI (save/load/autosave entry points, missing-file dialogs); QA (round-trip and recovery tests); Inspector (document dual formats, read-only).

### Risks

- Quiet unify of Python `.daw` schema 1.0 with C++ `SongDocument` schema 1.0.0 — **forbidden unless approved**.
- Autosave calling `save_project` and rotating backups as if they were user saves.
- Missing-media paths that rewrite the project on load.
- Migration that drops unknown keys.

### Required tests

Round-trip of a realistic session (tracks, audio clip refs, MIDI clips, mixer, routes). Crash mid-write preserves the previous good `.daw` (already covered in `tests/test_project.py` — do not invent additional counts). Autosave writes valid JSON without replacing the user file. Missing required keys still raise. Missing audio files are reported, not silently dropped. Record actual QA counts when the milestone runs.

### Completion gate

QA confirms save → close → reopen session integrity, recovery, and that **both formats still exist and are documented**. Completion report. Stop for approval.

### Task inventory

- Document dual formats in-repo (Python `.daw` 1.0 vs C++ `SongDocument` 1.0.0): owners, on-disk location, what each serializes, what is out of scope. **Do not unify.**
- Complete project serialization inventory (what `save_project` actually writes vs live UI/engine state).
- Track state persistence (name, mute, solo, volume, pan, instrument, routing key from M1).
- Confirm routing persistence still round-trips after M2 changes (regression of M1).
- MIDI state persistence (`midi_clips` / `MidiClip.to_dict`).
- Mixer state persistence.
- Timeline state (zoom, clips placement, bpm).
- Plugin/effect state when supported (placeholder rack only unless a later approved milestone added real inserts).
- Crash recovery validation (backup + atomic write; reopen last good file).
- Autosave behavior (`ProjectManager.autosave` vs UI calling `save_project`).
- Missing-file handling (audio refs that do not exist).
- Project migration/version handling (`migrate_project` is currently a stub for `1.0`).
- Corruption/error handling (invalid JSON, missing keys — already raises; keep that).
- Regression tests for save/load (existing `tests/test_project.py` plus session-level round-trip). Do not invent counts.

---

## Milestone 3 — Mixer

**Status:** PLANNING ONLY.
**Name:** Mixer.

### Objective

Create a usable DAW mixer on top of M1 routing and persisted session state.

### Definition of done

Channel strips expose volume, pan, mute, solo, metering, naming, master, buses, sends, insert slots, and routing controls. Mixer state persists. Tests cover mix math and UI-to-engine wiring.

### Dependencies

M1 (routing, buses, sends) approved; M2 persist of mixer fields. Current code: `src/track_panel.py` already has per-track volume/pan/mute/solo widgets; `src/audio_engine.py` mix path; no dedicated mixer metering/bus strips yet.

### Responsible seated roles

Engine (mix math, meters, bus/send levels); UI (mixer view); Core (persist mixer state in `.daw`); QA (mixer tests); Inspector (map current TrackPanel vs desired mixer).

### Risks

- Rebuilding routing inside the mixer instead of calling Engine dest APIs.
- Metering on the UI thread blocking playback.
- Solo/mute rules that disagree with routed graphs (a muted dest must silence sources that output to it — define and test).

### Required tests

Volume/pan/mute/solo vs mix output. Solo exclusivity. Master fader. Bus/send level. Persistence of mixer fields. Meter values are finite and non-blocking. Regression of M1 dest-fader tests.

### Completion gate

QA signs off mixer + persist + routing regression. Completion report. Stop for approval.

### Task inventory

- Channel strips (one strip per track, wired to Engine).
- Volume.
- Pan.
- Mute.
- Solo (define solo vs routed sources).
- Metering (peak; document RMS if added).
- Master channel.
- Bus channels (depends on M1 buses).
- Sends (depends on M1 sends).
- Insert slots (UI slots; processing belongs to M8).
- Routing controls (reuse M1 dest picker).
- Channel naming.
- Mixer state persistence.
- Mixer tests.

---

## Milestone 4 — Audio track workflow

**Status:** PLANNING ONLY.
**Name:** Audio track workflow.

### Objective

Make recorded/imported audio practical to edit on the timeline.

### Definition of done

Import, place, move, trim, split, delete, duplicate, copy/paste, fades, clip gain, looping, snap, timeline sync, and waveform display work for audio clips. Undo/redo **integration points** exist even if the full command stack is M11. Audio-editing tests pass.

### Dependencies

M2 session integrity; playback path already honors clip start/trim (`src/audio_engine.py`, Aug 22 slice). `src/clip.py` already has trim/split/fade/copy primitives — workflow is wiring + correctness, not a greenfield editor.

### Responsible seated roles

Engine (playback of edited clips); Core (clip persistence); UI (timeline gestures, waveform); QA (audio-editing tests); Inspector (clip field alias map already in engine — keep it accurate).

### Risks

- Edits that change files on disk instead of clip region.
- Timeline start vs file trim confusion (engine already has alias keys — do not fork another schema).
- Looping that desyncs from transport.

### Required tests

Place/move/trim/split/fade/gain against mix output and `.daw` round-trip. Snap. Copy/paste does not alias mutable buffers unsafely. Do not invent counts.

### Completion gate

QA confirms a user can import a WAV, edit it on the timeline, save, reopen, and hear the same arrangement. Completion report. Stop.

### Task inventory

- Import audio onto a track.
- Placement on the timeline.
- Move.
- Trim.
- Split.
- Delete.
- Duplicate.
- Copy/paste.
- Fade in/out.
- Clip gain.
- Looping.
- Snap behavior.
- Timeline synchronization with transport.
- Waveform display improvements.
- Undo/redo integration points (full stack is M11).
- Audio-editing tests.

---

## Milestone 5 — MIDI workflow

**Status:** PLANNING ONLY.
**Name:** MIDI workflow.

### Objective

Make MIDI editing usable as a real composition environment.

### Definition of done

Create MIDI clips; edit notes in the piano roll (create/delete/move/resize/velocity); quantize; snap; copy/paste; loop; channel handling; playback stays in sync; persist; undo/redo integration; MIDI tests pass.

**Do not introduce FluidSynth unless separately approved.** Current local synth is `src/midi_synth.py` + piano roll `src/piano_roll.py` + `src/midi_clip.py`. Keep that path.

### Dependencies

M2 MIDI persist; playback already renders `MidiClip` via `midi_synth` (local, not GitHub). M1 dest routing already follows MIDI buffers.

### Responsible seated roles

Engine (render/sync); UI (piano roll); Core (MIDI persist); QA (MIDI tests); Inspector (map MidiClip vs piano-roll vs engine load).

### Risks

- Pulling in FluidSynth “just for quality.”
- Piano-roll edits that do not write `MidiClip` / `.daw`.
- Timing drift vs audio clips on the same timeline.

### Required tests

Note CRUD; velocity; quantize; persist round-trip; Play renders notes; dest routing still applies (M1 regression). Existing MIDI tests live under `tests/test_midi_clip.py`, `tests/test_midi_synth.py`, `tests/test_play_renders_midiclip.py` — re-run; do not invent totals.

### Completion gate

QA confirms compose-in-piano-roll → Play → save → reopen. No FluidSynth. Completion report. Stop.

### Task inventory

- MIDI clip creation.
- Piano-roll editing.
- Note creation.
- Delete.
- Move.
- Resize.
- Velocity editing.
- Quantization.
- Snap.
- Copy/paste.
- Looping.
- MIDI channel handling.
- MIDI playback synchronization.
- Undo/redo integration (full stack M11).
- MIDI persistence.
- MIDI tests.
- Explicit non-goal: FluidSynth (planning note only).

---

## Milestone 6 — Transport and timeline

**Status:** PLANNING ONLY.
**Name:** Transport and timeline.

### Objective

Make the transport reliable enough for normal DAW use.

### Definition of done

Play, pause, stop, return to start, seek, accurate playhead, loop regions, tempo, time signature, ruler, grid, snap, song position, persisted transport state, and keyboard shortcuts work. Synchronization tests pass.

### Dependencies

Playback slice (already local); M4/M5 clip timing; `src/transport_controls.py` already holds bpm / time signature / metronome / position.

### Responsible seated roles

Engine (clock, seek, loop); UI (transport, ruler, shortcuts); Core (persist transport block in `.daw`); QA (sync tests).

### Risks

- Playhead UI timer drifting from mix position (historical 50ms playhead-only bug — do not regress).
- Loop that ignores MIDI vs audio differently.
- Tempo change that does not re-render MIDI buffers.

### Required tests

Play/pause/stop/seek position. Loop region. Tempo change vs MIDI. Space-bar shortcut. Persist transport. Regression of play-loads-clips / playback-path tests. Do not invent counts.

### Completion gate

QA confirms transport matches audible playback and persisted position. Completion report. Stop.

### Task inventory

- Play.
- Pause.
- Stop.
- Return to start.
- Seek.
- Playhead accuracy.
- Loop regions.
- Tempo.
- Time signature.
- Timeline ruler.
- Grid.
- Snap.
- Song position.
- Transport state persistence.
- Keyboard shortcuts.
- Synchronization tests.

---

## Milestone 7 — Recording

**Status:** PLANNING ONLY.
**Name:** Recording.

### Objective

Allow reliable audio and MIDI recording.

### Definition of done

User can select input, arm a track, record audio and MIDI with count-in/metronome/monitoring, place the take on the timeline, recover a crashed record, and pass recording tests. Basic punch only if architecture supports it without a rewrite.

### Dependencies

M4/M5/M6. Device I/O via existing `sounddevice` path where present. File write must use Core-safe patterns (do not invent a new save stack).

### Responsible seated roles

Engine (capture, latency, monitoring); Core (recorded file management, recovery); UI (arm, meters, device picker); QA (recording tests).

### Risks

- Recording that bypasses `.daw` and leaves orphan files.
- Latency not documented, so punch is unusable.
- MIDI record into a format FluidSynth-shaped — stay on `MidiClip`.

### Required tests

Arm + record audio file appears and plays back. MIDI record creates notes. Crash during record leaves a recoverable take or a clean failure. Input device missing fails clearly.

### Completion gate

QA records audio and MIDI, reopens, hears/sees the take. Completion report. Stop.

### Task inventory

- Input device selection.
- Track arm.
- Audio recording.
- MIDI recording.
- Count-in.
- Metronome.
- Monitoring.
- Recording placement on the timeline.
- Takes.
- Basic punch workflow if architecture supports it.
- Latency handling.
- Recorded file management.
- Recording recovery.
- Recording tests.

---

## Milestone 8 — Effects architecture

**Status:** PLANNING ONLY.
**Name:** Effects and processing architecture.

### Objective

Create a stable processing chain in the **Python** engine.

**Do not automatically begin JUCE or C++ work. Keep JUCE on hold unless explicitly approved.**

### Definition of done

Insert slots, enable/bypass, reorder, parameter state, channel/bus/master processing, preset persistence, failure isolation, and tests exist for the supported built-in (or already-present placeholder) effects. No VST/AU/CLAP host unless separately approved.

### Dependencies

M1 inserts/routing integration; M3 insert slots UI. Current `src/effects_rack.py` is UI/placeholders — plan from that, do not assume real DSP.

### Responsible seated roles

Engine (chain, bypass, isolation); UI (rack); Core (parameter/preset persist); QA (tests). JUCE role stays unseated.

### Risks

- Starting Tracktion/JUCE plugin hosting under this milestone.
- Real-time unsafe Python DSP; document offline-vs-realtime clearly.
- Effect crash taking down the mix thread.

### Required tests

Bypass equals dry. Reorder changes sound deterministically for a known processor. Bad effect does not kill playback. Persist parameters. Regression of dry mix / routing.

### Completion gate

QA confirms a chain on a track and on master, persist, bypass, isolation. No JUCE. Completion report. Stop.

### Task inventory

- Insert architecture.
- Effect slots.
- Enable/bypass.
- Reordering.
- Parameter state.
- Processing chain.
- Bus processing.
- Master processing.
- Preset/state persistence.
- Failure isolation.
- CPU/error handling.
- Tests.
- Explicit non-goal: JUCE / C++ / VST host.

---

## Milestone 9 — Automation

**Status:** PLANNING ONLY.
**Name:** Automation.

### Objective

Allow parameters to change over time.

### Definition of done

Automation lanes for volume, pan, sends, and supported effect parameters; nodes/points editable; playback follows curves; persist; undo/redo integration; tests pass.

### Dependencies

M3 mixer, M6 transport, M8 for effect parameters. Routing send levels from M1.

### Responsible seated roles

Engine (playback of curves); UI (lanes/points); Core (persist); QA (automation tests).

### Risks

- Automation that fights static fader state on load.
- Sample-accurate claims the Python mix path cannot keep.

### Required tests

Volume lane silences a region. Persist points. Disable automation holds last/static value as documented.

### Completion gate

QA rides a volume ride, saves, reopens, hears it. Completion report. Stop.

### Task inventory

- Automation lanes.
- Volume automation.
- Pan automation.
- Send automation.
- Supported effect parameter automation.
- Nodes/points.
- Editing.
- Playback.
- Persistence.
- Undo/redo integration (full stack M11).
- Automation testing.

---

## Milestone 10 — UI completion

**Status:** PLANNING ONLY.
**Name:** User interface completion.

### Objective

Turn the functional shell into a coherent DAW interface.

### Definition of done

Arrangement, track headers, mixer, inspector, routing controls, browser where appropriate, piano roll, transport, menus, context menus, shortcuts, resize, window management, selection consistency, error dialogs, empty states, and readability hold together. UI regression testing exists.

### Dependencies

M3–M9 features that the UI must surface. Current shell: `src/main_window.py`, `timeline.py`, `track_panel.py`, `piano_roll.py`, `chat_widget.py`, `transport_controls.py`.

### Responsible seated roles

UI (primary); Engine/Core only for missing hooks; QA (UI regression); Inspector (view-to-state map).

### Risks

- Redesigning the app instead of completing the shell.
- New AI chat chrome (M13/M14 only, and only when approved).
- Selection model forking from `src/selection_model.py`.

### Required tests

Smoke: new project, add tracks, open mixer/piano roll/transport, resize, error dialog on missing file. Keyboard shortcuts from README that are actually wired. Do not invent counts.

### Completion gate

QA walkthrough of empty states + a loaded session. Completion report. Stop.

### Task inventory

- Main arrangement view.
- Track headers.
- Mixer view consistency with M3.
- Inspector.
- Routing controls (M1 picker surfaced cleanly).
- Browser where appropriate.
- Piano roll.
- Transport.
- Menus.
- Context menus.
- Keyboard shortcuts.
- Resize behavior.
- Window management.
- Selection consistency.
- Error dialogs.
- Empty states.
- Accessibility/readability.
- UI regression testing.

---

## Milestone 11 — Undo/redo command system

**Status:** PLANNING ONLY.
**Name:** Undo/redo and command system.

### Objective

Ensure destructive and editing actions are safely reversible.

### Definition of done

A command architecture covers audio edits, MIDI edits, mixer, routing, automation, and project changes. Undo/redo and history keep state consistent. Tests prove restore.

### Dependencies

M4–M10 integration points. Do not wait until M11 to avoid destroying data — earlier milestones only need hooks; M11 is the stack.

### Responsible seated roles

Core (command stack, project apply); Engine (engine-state apply); UI (undo/redo actions); QA (state consistency tests).

### Risks

- Partial undo that restores UI but not engine (or the reverse).
- Unlimited history vs `.daw` size.
- AI later bypassing the stack (M13 must use this system).

### Required tests

Undo/redo pairs for: clip move, note edit, fader, dest route, automation point. History does not leak muted engine buffers. Do not invent counts.

### Completion gate

QA undoes/redoes across audio, MIDI, mixer, routing. Completion report. Stop.

### Task inventory

- Command architecture.
- Undo.
- Redo.
- Edit history.
- Audio edits.
- MIDI edits.
- Mixer changes.
- Routing changes.
- Automation changes.
- Project changes.
- State consistency tests.

---

## Milestone 12 — Performance and stability

**Status:** PLANNING ONLY.
**Name:** Performance and stability.

### Objective

Make the DAW reliable under realistic sessions.

### Definition of done

Larger track counts, longer sessions, WAV+MIDI, routing stress, memory/CPU, UI responsiveness, playback stability, save/load stress, crash/recovery, logging, and error isolation are measured and acceptable for v1 use.

### Dependencies

M1–M11 features that will be stressed. Logging should not wait for new roles.

### Responsible seated roles

Engine (CPU/memory/playback); Core (save/load stress, logging); UI (responsiveness); QA (stress/crash tests); Inspector (baseline map).

### Risks

- Optimizing C++/JUCE instead of the Python path actually shipping.
- Stress tests that require hardware not present in CI — document offline mix path.

### Required tests

Documented track-count and session-length fixtures. Routing cycle still rejected under load. Save/load of a large project. Crash injection on write (M2 pattern). Record actual numbers; do not invent them here.

### Completion gate

QA reports baselines and no crash-level blockers on the agreed fixture. Completion report. Stop.

### Task inventory

- Larger track counts.
- Longer sessions.
- WAV + MIDI combinations.
- Routing stress tests.
- Memory behavior.
- CPU behavior.
- UI responsiveness.
- Playback stability.
- Save/load stress testing.
- Crash testing.
- Recovery testing.
- Logging.
- Error isolation.

---

## Milestone 13 — AI assistant foundation

**Status:** PLANNING ONLY. **Do not execute. No OpenJarvis. No new AI roles.**
**Name:** AI assistant integration foundation.

### Objective

**Plan** how existing `AgentManager` architecture connects to safe DAW actions through the command/state stack. Dependable DAW first.

### Definition of done (planning)

A written design (Notion + this milestone task) covering tool/action interface, permission boundaries, session inspection, safe command execution, change preview, reversible AI actions, AI action history, failure handling, and agent testing. **No new AI systems shipped.**

### Dependencies

M11 command system (AI must not bypass it). Existing `src/agent_manager.py` apply path. OpenJarvis remains **not approved**.

### Responsible seated roles

Inspector (map current AgentManager/chat apply — read-only); Core (command/permission design); Engine (what audio mutations are legal); UI (preview/history chrome — plan only); QA (agent-test plan). Do **not** seat JUCE or new AI roles.

### Risks

- “Just wire OpenJarvis” during planning.
- AI writing `.daw` or engine buffers off the command stack.
- New specialist roles.

### Required tests

Planning: list the tests that will be required when this milestone is approved (apply preview, reject unauthorized mutation, undo AI action). Do not run a new AI implementation.

### Completion gate

Design accepted by Daniel. **No code execution in this milestone until that approval explicitly includes implementation.** Completion report. Stop.

### Task inventory (plan only)

- Tool/action interface design.
- Permission boundaries.
- Session inspection.
- Safe command execution (via M11).
- Change preview.
- Reversible AI actions.
- AI action history.
- Failure handling.
- Agent testing plan.
- Explicit non-goals: OpenJarvis, new AI systems, new AI roles.

---

## Milestone 14 — AI music workflows

**Status:** PLANNING ONLY. **Do not execute.**
**Name:** AI music workflows.

### Objective

Plan later capabilities that use the M13 tool interface: create tracks, arrange, edit MIDI, suggest/apply mix changes, session analysis, composition/production assistance, context-aware guidance.

### Definition of done (planning)

Each capability is specified as commands against established DAW state — never as a bypass. No implementation until Daniel approves M13 **and** this milestone.

### Dependencies

M13 design approved; M4–M11 actually exist so the tools have real targets.

### Responsible seated roles

Same seated roster. No new AI roles. Inspector maps current AgentManager “apply session” vs desired tools.

### Risks

- Shipping generation quality work (ElevenLabs, OpenJarvis, new models) instead of safe tools.
- Product-agent pipeline (Producer → Conductor → Track Agents) confused with the engineering roster.

### Required tests

Planning only: every AI action has an undo test and a permission test on the command stack.

### Completion gate

Daniel approval to implement specific workflows, one at a time. Stop.

### Task inventory (plan only)

- Create tracks (via DAW commands).
- Arrange session.
- Edit MIDI.
- Suggest mix adjustments.
- Apply approved mix changes.
- Session analysis.
- Composition assistance.
- Production assistance.
- Context-aware project guidance.
- Rule: every AI action uses established command/state architecture; no bypass.

---

## Milestone 15 — File and asset management

**Status:** PLANNING ONLY.
**Name:** File and asset management.

### Objective

Make session assets reliable and portable.

### Definition of done

Audio refs, relative paths, missing-media handling, relink, project folders, imported vs recorded media, duplicate handling, safe project move, cleanup, and backup behavior work. There is still **no** silent unify with C++ project files.

### Dependencies

M2 session reliability; M7 recorded files. `ProjectManager` already has `.backups` and `.autosave`.

### Responsible seated roles

Core (paths, registry, backups); UI (relink dialogs); Engine (does not hold exclusive file locks across save); QA (missing/relink/move tests); Inspector (asset inventory).

### Risks

- Absolute Windows paths from the original prototype (`C:\Users\djohn\...`) breaking portability.
- Cleanup deleting user media.

### Required tests

Move project folder, reopen, audio still resolves or relink is offered. Missing file does not crash. Backup rotation still ≤ 10 (existing test in `tests/test_project.py`).

### Completion gate

QA relocates a project and recovers missing media. Completion report. Stop.

### Task inventory

- Audio file references.
- Relative paths.
- Missing media handling.
- Relink workflow.
- Project folders.
- Imported media.
- Recorded media.
- Duplicate handling.
- Safe project movement.
- Asset cleanup.
- Backup behavior.

---

## Milestone 16 — Export / render

**Status:** PLANNING ONLY.
**Name:** Export / render.

### Objective

Allow the user to create finished audio files.

### Definition of done

Master render to WAV and other already-supported formats, with sample rate, bit depth, range, full-song and (if appropriate) selection export, progress/error handling, and validation tests. Routing/mixer/effects in the render match playback.

### Dependencies

M1 routing, M3 mixer, M8 chain, M6 range/loop. `src/export_dialog.py` already exists — inspect before rewriting.

### Responsible seated roles

Engine (offline render using mix path); UI (export dialog); Core (export settings); QA (file validation).

### Risks

- Export that ignores dest routing (must use the same mix as Play).
- Format support claimed in README (MP3/FLAC) that is not actually wired — QA must verify, not trust README.

### Required tests

Export WAV is valid and matches offline `mix()` within documented tolerance. Dest-fader case from M1 still applies. Failed disk write does not corrupt `.daw`.

### Completion gate

QA renders a mixed song and validates the file. Completion report. Stop.

### Task inventory

- Master render.
- WAV export.
- Supported formats (verify vs code, not README).
- Sample rate.
- Bit depth.
- Render range.
- Full-song export.
- Selection export if appropriate.
- Progress/error handling.
- Export validation tests.

---

## Milestone 17 — Application settings

**Status:** PLANNING ONLY.
**Name:** Application settings.

### Objective

Create persistent user-level configuration (not project state).

### Definition of done

Audio, MIDI, interface, default project, file paths, autosave, and performance settings persist and can reset to defaults.

### Dependencies

M6 devices/transport, M7 inputs, M12 performance knobs. Do not store these only inside a `.daw`.

### Responsible seated roles

Core (prefs file); UI (settings dialog); Engine (applies audio/MIDI device settings); QA (persist/reset).

### Risks

- Settings that silently override project bpm/routing.
- API keys / `.env` treated as “settings” and committed. `.env.example` exists; do not write secrets into `.daw` or git.

### Required tests

Change a setting, restart app, it remains. Reset restores defaults. Invalid device fails closed.

### Completion gate

QA restart-persist + reset. Completion report. Stop.

### Task inventory

- Audio settings.
- MIDI settings.
- Interface settings.
- Default project behavior.
- File paths.
- Autosave settings.
- Performance settings.
- Preference persistence.
- Reset/default behavior.

---

## Milestone 18 — Release hardening

**Status:** PLANNING ONLY.
**Name:** Release hardening.

### Objective

Prepare the application for actual use outside development.

### Definition of done

Full regression, integration, clean-install, upgrade, project compatibility, crash/recovery, performance baseline, logging, dependency audit, packaging, version info, release notes, known issues.

### Dependencies

M1–M17 complete enough to freeze a feature set. GitHub catch-up is **still not implied** — packaging may be local until Daniel approves a push.

### Responsible seated roles

QA (suites, sign-off); Core (version, compatibility); Engine (perf baseline); UI (clean-install smoke); Inspector (known-issues list).

### Risks

- Treating GitHub `main` as the release source while local is ahead.
- Packaging JUCE bits that are not the running app.

### Required tests

Full existing pytest suite (record the actual count at the time). Clean-install smoke. Open a schema 1.0 `.daw` from before routing (missing `track_outputs` = master). Crash-recovery from M2.

### Completion gate

QA known-issues list + passing regression. Completion report. Stop.

### Task inventory

- Full regression suite.
- Integration tests.
- Clean-install test.
- Upgrade test.
- Project compatibility test.
- Crash/recovery testing.
- Performance baseline.
- Error logging.
- Dependency audit.
- Packaging.
- Version information.
- Release notes.
- Known issues.

---

## Milestone 19 — Release candidate

**Status:** PLANNING ONLY.
**Name:** Release candidate.

### Objective

Create a build that could reasonably be called version 1.0.

### Definition of done

Core DAW workflows function end-to-end: existing project opens; audio playback; MIDI; routing; mixer; editing; recording; saving/loading; export; major controls persist; no known data-loss bugs; no known crash-level blockers; regression suite passes; QA signs off.

### Dependencies

M18 hardening. User DoD (M20) is the acceptance script for the RC.

### Responsible seated roles

QA (sign-off); all seated roles for RC bugs only — no new features, no JUCE, no AI expansion.

### Risks

- Feature sneak-ins.
- Signing off against GitHub instead of local.

### Required tests

M20’s 15-point user script run by QA on the RC build, plus the regression suite with the count QA records that day.

### Completion gate

QA RC sign-off. Completion report. Stop. Daniel decides whether to call it 1.0.

### Task inventory

- Core DAW workflows end-to-end.
- Existing project opens correctly.
- Audio playback works.
- MIDI works.
- Routing works.
- Mixer works.
- Editing works.
- Recording works.
- Saving/loading works.
- Export works.
- Major controls persist.
- No known data-loss bugs.
- No known crash-level blockers.
- Regression suite passes (actual count).
- QA signs off.

---

## Milestone 20 — Version 1.0 complete

**Status:** PLANNING ONLY.
**Name:** Version 1.0 complete.

### Objective

Ship a finished, stable, usable application against the user definition of done. Dependable DAW first; approved AI only through safety systems.

### Definition of done (15-point user DoD)

A user can:

1. Create a project.
2. Add audio and MIDI tracks.
3. Import or record material.
4. Arrange material on the timeline.
5. Edit audio and MIDI.
6. Route tracks.
7. Mix tracks.
8. Use buses, sends and supported processing.
9. Save the project.
10. Close the application.
11. Reopen the project with the session intact.
12. Continue editing.
13. Render/export a finished song.
14. Recover safely from common failures.
15. Use approved AI functionality without bypassing project safety systems.

QA must independently confirm the release criteria.

If M13/M14 were never approved, point 15 is satisfied by: **no unapproved AI surface**, and any existing AgentManager apply path still goes through project safety (command/save/validate) rather than bypassing it. Do not implement new AI to check the box.

### Dependencies

M19 RC QA sign-off. Local `/workspace/aria` remains source of truth unless Daniel approved a GitHub catch-up.

### Responsible seated roles

QA (independent 15-point run); Inspector (read-only confirmation of what shipped vs plan); Core/Engine/UI only for release-blocking fixes.

### Risks

- Declaring 1.0 while GitHub is behind and no one can reproduce from local.
- Implementing OpenJarvis to “finish” point 15.
- Unifying `.daw` / `SongDocument` at the last minute.

### Required tests

Independent QA execution of the 15 points above, plus regression suite with the count actually run. No invented totals.

### Completion gate

QA independent confirm of all 15 points. Completion report to Daniel. Version identifier recorded. **Stop.** Further work is a new approved milestone, not silent scope.

### Task inventory

- Run 15-point user DoD (QA, independent).
- Confirm session intact after save/close/reopen (points 9–12).
- Confirm routing + mixer + buses/sends/processing (points 6–8) against M1/M3/M8 deliverables that actually shipped.
- Confirm export (point 13) against M16.
- Confirm recovery (point 14) against M2/M7/M12.
- Confirm AI safety (point 15) against approved M13/M14 **or** explicit non-ship.
- Record known limitations and deferred items (FluidSynth, format unify, JUCE, GitHub catch-up, OpenJarvis) as **not in 1.0** unless separately approved.
- Final completion report.

---

## Daily loop

Weekdays **9:00 America/Chicago**.

1. **Read context** — ClickUp current milestone + incomplete tasks; Notion yesterday; QA results; unresolved blockers; **actual local repo** `/workspace/aria`. Never rely only on an old roadmap if implementation changed.
2. **Choose 3** from the **CURRENT approved milestone only** (today: M1). Build on completed work. Independently testable. No future-milestone pull if today’s batch finishes early.
3. **Plan ClickUp daily batch** — parent “Daily Batch — [date]” under the approved milestone; each task has objective, files/modules, acceptance criteria, required tests, owner, status (`BACKLOG` / `TODAY` / `IN PROGRESS` / `QA` / `BLOCKED` / `DONE`). Until ClickUp write is available (~2026-08-28 07:00 America/Chicago), this file is the plan.
4. **Calendar** — one event, title `AI DAW — [Milestone] — Daily Increment`, America/Boise, availability FREE. Description lists TASK 1/2/3, current milestone, today’s objective, ClickUp refs when they exist.
5. **Assign** Engine / Core / UI / QA (Inspector if a map is needed). Do not seat JUCE or new AI roles. Do not expand scope without approval.
6. **Test** each task. Evidence: unit, integration, regression, manual checks, logs. Code written ≠ DONE.
7. **Independent QA** — tests run/passed/failed, regression, unexpected behavior, unauthorized source changes, scope violations. Cannot mark DONE until required QA passes.
8. **Update ClickUp** — DONE / QA / BLOCKED / carry forward. Do not hide incomplete work behind replacement tasks.
9. **Notion journal** — one child page per increment with the required sections, including CONTEXT FOR TOMORROW written so another engineer can continue without guessing.
10. **Update the same calendar event** with OUTCOME (per-task DONE/QA/BLOCKED, QA brief, Notion ref, next increment). No disconnected duplicate event.

Tomorrow’s three tasks come from today’s actual outcome, remaining DoD, bugs, QA, and blockers — **not** from pre-dated batches.

When the approved milestone looks complete: completion review + report + **stop**. Do not start the next milestone without Daniel’s approval.

### Daily report to Daniel (after the loop)

```
DAILY AI DAW REPORT
Milestone:
Today’s three tasks:
1. [status] — task
2. [status] — task
3. [status] — task
What works now:
QA:
Problems:
ClickUp: Updated / issue
Notion: Development log updated / issue
Calendar: Plan + outcome updated / issue
Next likely three:
1.
2.
3.
Blocker requiring my decision: None / description
```

Closed loop: READ CONTEXT → CHOOSE 3 → PLAN IN CLICKUP → TIMEBOX IN CALENDAR → BUILD → TEST → QA → UPDATE CLICKUP → DOCUMENT IN NOTION → UPDATE CALENDAR WITH OUTCOME → USE THAT CONTEXT TOMORROW.

---

## GitHub

Repo: `https://github.com/DJ848arch/AI-powered-DAW-V2`

`main` is behind local `/workspace/aria` (Aug 22 playback slice only: UI wired to AudioEngine, mix honors clip start/trim). Subsequent local work (MIDI piano roll, AgentManager apply, crash-safe save, routing slice 1) is **not** on GitHub.

**Do not catch up unless Daniel approves.** Do not clone. Do not push. Local is source of truth. Document local-vs-GitHub drift in Notion when relevant. GitHub catch-up is not an M1 task and is not implied by M18 packaging.

---

## ClickUp import (landed 2026-08-28)

- Folder **AI-Powered DAW** `901412060516` in space `90145572472`.
- List **M1 Routing — APPROVED** `901419670127`. 2026-08-27 batch DONE (`86bbpakq7`). 2026-08-28 batch IN PROGRESS (`86bbpakpu`). Remaining M1 backlog imported (sends, send levels, inserts, expanded tests, regression, completion review).
- List **Roadmap — planning only** `901419670128`. M2–M20 imported as planning shells. Do not execute.
- Existing ARIA list `901419614214` / task `86bbngfza` retitled **M1 Routing — APPROVED**.
- Native statuses only (`to do` / `in progress` / `complete`). Tags were not created (space tags may not exist).
- NoteFluent: folder `901412012033` and list `901419614218` renamed off As Written.
