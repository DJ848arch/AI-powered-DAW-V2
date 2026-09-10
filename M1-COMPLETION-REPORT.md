# MILESTONE COMPLETION REPORT — M1 Routing Core

**Date:** 2026-09-02
**Local:** `/workspace/aria` (source of truth)
**ClickUp:** 86bbpakue
**Status:** COMPLETE vs Definition of Done. Awaiting Daniel’s approval. **STOP. Do not start M2.**

## Milestone

M1 Routing Core — reliable internal signal routing in the Python engine, persisted in `.daw` (schema 1.0 additive).

## Status

DoD satisfied. Independent QA PASS. Inspector read-only YES on every DoD bullet. No unresolved routing blocker.

## What was built

- Track → Master (default) and Track → Track in `audio_engine`
- Persist/restore `track_outputs` and named `buses` in `.daw` via ProjectManager (schema stays 1.0)
- Cycle detection beyond self-output; invalid route rejection; read-only graph validation
- Dest UI picker (Master + other tracks + known buses, never self)
- Bus architecture (mix to master; unused buses survive File>Open after 86bbtn53e)
- Sends and send levels on the engine mix path (post-fader extra; in-memory only)
- Inserts/routing order: clips → inserts (identity/test-hook) → fader → split main + sends

## What now works

A user (and tests) can route Track→Master, Track→Track, and Track→named bus; save/open `.daw` and keep dests and unused buses; cycles and invalid dests are rejected; dest picker stays in sync; default master mix is unchanged.

Sends/send levels work in the current session only (not saved). Inserts are dry/identity, not a real effects host.

## Tests

Final independent regression (2026-09-02):

`QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m pytest tests/ -q`

**132 passed, 0 failed, 0 skipped, 0 xfailed** (QA 1.78s; Inspector 132 confirmed).

Morning baseline was 131 passed / 1 xfailed. The unused-bus File>Open xfail is now a pass.

## QA

Independent QA gated every M1 slice. Today: residual 86bbtn53e and regression 86bbpakuc PASS, then QA DoD confirmation. Inspector independently mapped each ROADMAP bullet YES.

## Known limitations

- Sends and send levels are not in `.daw` / `get_state` (in-memory mix graph only)
- No send UI; dest picker has no send controls
- Inserts are identity + `set_test_insert` / `_insert_processor` only (real DSP is later)
- No bus fader; buses mix to master only
- Mix is one-hop (cycles blocked in setter/validator, not a recursive mix walker)
- Dual formats remain: Python `.daw` 1.0 vs C++ `SongDocument` 1.0.0. Not unified.
- GitHub `DJ848arch/AI-powered-DAW-V2` main is still the Aug 22 playback slice. Local M1 is unpushed.

## Technical debt

- `engine.get_state()` has no `buses` field; Core collects via `list_buses()` on save
- `migrate_project` is a stub for 1.0
- ROADMAP.md / CADENCE.md lagged the tree during M1 (report is the current record)

## Deferred items (do not execute)

- M2 and later milestones
- GitHub catch-up
- FluidSynth (stay on `midi_synth.py`)
- Schema unify / schema 3.0
- JUCE / `aria-cpp` audio routing
- OpenJarvis / new AI
- Real insert DSP (M8)
- Send persist + send UI (reasonable M3 mixer follow-on, not silently M1)

## Recommendation for next milestone

Call **M1 complete locally**. **STOP.** Do not start M2, GitHub, FluidSynth, format unify, JUCE, or new AI until Daniel approves a next milestone.
