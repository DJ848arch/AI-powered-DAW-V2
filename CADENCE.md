# ARIA daily routing

Weekdays 9:00 local. Chief of Staff coordinates. Specialists do not message Daniel.
Daniel switched this from a Monday weekly ship on 2026-08-27. Effective immediately.

Dependable DAW first. No new AI until playback, timing, routing, and persistence are reliable.

## Approved work lives on ClickUp

List: ARIA `901419614214` in workspace `90141241740`.
Repo: https://github.com/DJ848arch/AI-powered-DAW-V2

If ClickUp has approved open goals: work the highest, in a small daily increment. Fix anything that breaks Play/save/tests first.
If ClickUp has no approved goals: propose goals to Daniel. Do not start them until he approves.

## Current approved goals (Daniel, 2026-09-09 evening)

- M1 Routing Core approved. M2 ordered: Real Audio Graph + Schema Unification.
- THIS increment: first three only — schema audit + authoritative model (`SCHEMA.md`), `.daw` load/save on schema 1.1 with M1 compat, regression + round-trip tests.
- Engine stays authoritative for signal flow. No FluidSynth, JUCE, OpenJarvis, C++ Edit, new AI. No real insert DSP / send-audio / bus-mixer / metering this slice.
- C++ `SongDocument` remains a separate format (do not unify).

ClickUp task id `86bbngfza` (retitled **M1 Routing — APPROVED** on 2026-08-28). Daily work lives in folder AI-Powered DAW / list M1 Routing — APPROVED (`901419670127`).

## After each session, tell Daniel

1. What was completed
2. What is working now
3. What remains for routing
4. Any blocker that needs a decision from him

No new scope without his approval.

## Roster

- Inspector — read-only map
- Core — project state, schema, save
- Engine — audio, MIDI, mixer, routing
- UI — PyQt
- QA — tests
- JUCE / new AI roles — on hold

Code via a Cursor cloud agent. Do not clone unless Daniel asks. Message only the specialist the current goal needs (Engine for routing). Never fan out the whole ARIA Engineering room.

## Slice 1 done (2026-08-27)

`set_track_output` / `get_track_output` in `src/audio_engine.py`. State key `track_outputs`. Track → master (default) or track → another track. Dest fader applies. Unknown dest and self-output rejected. tests/test_audio_engine_routing.py 5 passed. Local /workspace/aria only. Not on GitHub.

2026-08-28 increment (in progress): graph validation + dest UI picker + buses (model+mix). Still routing-only. No sends, inserts, GitHub catch-up, FluidSynth, JUCE, new AI.
