import re

# Fix agent_manager.py
with open('c:\\Users\\djohn\\.aria\\src\\agent_manager.py', 'r') as f:
    content = f.read()

# Fix the \n\n escape sequences and relative imports
content = content.replace('from enum import Enum\\n\\nfrom .diff_engine', 'from enum import Enum\n\nfrom diff_engine')
content = content.replace('from .diff_engine import', 'from diff_engine import')
content = content.replace('from .lock_manager import', 'from lock_manager import')

with open('c:\\Users\\djohn\\.aria\\src\\agent_manager.py', 'w') as f:
    f.write(content)

print('Fixed agent_manager.py')

# Fix agent_orchestrator_v2.py
with open('c:\\Users\\djohn\\.aria\\src\\agent_orchestrator_v2.py', 'r') as f:
    content = f.read()

# Fix the corrupted docstring
content = content.replace('"""Agent Orchestrator V2 - Enhanced agent system for v1.1 Architecture > header.txt && echo Provides streaming reasoning JSON parsing, diff preview, and multi-agent coordination"""', 
    '"""Agent Orchestrator V2 - Enhanced agent system for v1.1 Architecture\n\nProvides streaming reasoning JSON parsing, diff preview, and multi-agent coordination.\n"""')

# Fix relative imports
content = content.replace('from .diff_engine import', 'from diff_engine import')
content = content.replace('from .lock_manager import', 'from lock_manager import')
content = content.replace('from .selection_model import', 'from selection_model import')

with open('c:\\Users\\djohn\\.aria\\src\\agent_orchestrator_v2.py', 'w') as f:
    f.write(content)

print('Fixed agent_orchestrator_v2.py')
