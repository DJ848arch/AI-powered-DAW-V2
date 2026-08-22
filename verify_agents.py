"""Verify multi-agent system implementation"""
import sys
sys.path.insert(0, 'src')

from agent_manager import (
    AgentManager, AgentStage, AgentConfig, ProductionSession,
    BrainstormData, ProductionPlan, InstrumentationPlan, TrackData, MixingPlan
)

print('=== AGENT MANAGER VERIFICATION ===')
print(f'AgentStage enum values: {[s.value for s in AgentStage]}')
print(f'\nData classes available:')
print(f'  - BrainstormData: {BrainstormData}')
print(f'  - ProductionPlan: {ProductionPlan}')
print(f'  - InstrumentationPlan: {InstrumentationPlan}')
print(f'  - TrackData: {TrackData}')
print(f'  - MixingPlan: {MixingPlan}')

am = AgentManager()
print(f'\n=== AGENTS CONFIGURED ===')
for aid, name, desc, stage in am.get_agent_list():
    print(f'  {aid}: {name}')

print(f'\n=== TEST SESSION ===')
session_id = am.start_production_session()
print(f'Session created: {session_id[:8]}...')
print(f'Current stage: {am.get_current_stage(session_id)}')

print(f'\n=== ALL COMPONENTS VERIFIED SUCCESSFULLY ===')
