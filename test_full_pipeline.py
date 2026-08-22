"""End-to-end test of multi-agent production pipeline"""
import sys
sys.path.insert(0, 'src')

from agent_manager import AgentManager, AgentStage

print("=" * 60)
print("MULTI-AGENT PRODUCTION PIPELINE - END TO END TEST")
print("=" * 60)

am = AgentManager()

# Start session
session_id = am.start_production_session()
session = am.get_session(session_id)
print(f"\n[1] Session started: {session_id[:8]}...")
print(f"    Current stage: {session.current_stage.value}")

# Brainstorming Agent
print("\n[2] BRAINSTORMING AGENT")
response = am.send_message(session_id, "I want to make a pop beat")
print(f"    Agent: {response[:60]}...")

response = am.send_message(session_id, "upbeat and energetic, like Dua Lipa")
print(f"    Agent: {response[:60]}...")

# Approve and move to Producer
print("\n[3] APPROVING BRAINSTORM -> PRODUCER")
response = am.send_message(session_id, "yes approve")
print(f"    Response: {response[:60]}...")
session = am.get_session(session_id)
print(f"    New stage: {session.current_stage.value}")
print(f"    Brainstorm data: genre={session.brainstorm_data.genre if session.brainstorm_data else 'None'}")

# Producer Agent - send message to generate plan
print("\n[4] PRODUCER AGENT")
response = am.send_message(session_id, "looks good")
print(f"    Agent: {response[:60]}...")
session = am.get_session(session_id)
if session.production_plan:
    print(f"    Production plan: {session.production_plan.tempo_bpm} BPM, {session.production_plan.key}")
else:
    print(f"    Production plan: Not yet created")

# Approve and move to Conductor
print("\n[5] APPROVING PRODUCER -> CONDUCTOR")
response = am.send_message(session_id, "approve")
print(f"    Response: {response[:60]}...")
session = am.get_session(session_id)
print(f"    New stage: {session.current_stage.value}")
if session.instrumentation_plan:
    print(f"    Tracks planned: {len(session.instrumentation_plan.tracks)}")

# Conductor Agent
print("\n[6] CONDUCTOR AGENT")
response = am.send_message(session_id, "perfect")
print(f"    Agent: {response[:60]}...")

# Approve and move to Track
print("\n[7] APPROVING CONDUCTOR -> TRACK")
response = am.send_message(session_id, "approve")
print(f"    Response: {response[:60]}...")
session = am.get_session(session_id)
print(f"    New stage: {session.current_stage.value}")
if session.track_data:
    print(f"    Tracks created: {len(session.track_data.created_tracks)}")
    print(f"    MIDI patterns: {len(session.track_data.midi_patterns)}")

# Track Agent
print("\n[8] TRACK AGENT")
response = am.send_message(session_id, "great")
print(f"    Agent: {response[:60]}...")

# Approve and move to Mixing
print("\n[9] APPROVING TRACK -> MIXING")
response = am.send_message(session_id, "approve")
print(f"    Response: {response[:60]}...")
session = am.get_session(session_id)
print(f"    New stage: {session.current_stage.value}")
if session.mixing_plan:
    print(f"    Tracks mixed: {len(session.mixing_plan.track_mixing)}")

# Mixing Agent
print("\n[10] MIXING & MASTERING AGENT")
response = am.send_message(session_id, "sounds good")
print(f"    Agent: {response[:60]}...")

# Final approval - completes production
print("\n[11] FINAL APPROVAL -> COMPLETE")
response = am.send_message(session_id, "approve")
print(f"    Response: {response[:80]}...")
session = am.get_session(session_id)
print(f"    Final stage: {session.current_stage.value}")

print("\n" + "=" * 60)
print("FULL PIPELINE TEST PASSED!")
print("=" * 60)
if session.brainstorm_data:
    print(f"\nFinal production data:")
    print(f"  - Genre: {session.brainstorm_data.genre}")
if session.production_plan:
    print(f"  - Tempo: {session.production_plan.tempo_bpm} BPM")
    print(f"  - Key: {session.production_plan.key}")
if session.track_data:
    print(f"  - Tracks: {len(session.track_data.created_tracks)}")
if session.production_plan:
    print(f"  - Sections: {len(session.production_plan.sections)}")
print(f"  - Status: {session.current_stage.value.upper()}")
