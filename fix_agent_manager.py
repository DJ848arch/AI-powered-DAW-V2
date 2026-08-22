#!/usr/bin/env python3
"""Fix agent_manager.py corrupted imports"""

with open(r'c:\Users\djohn\.aria\src\agent_manager.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and fix the corrupted import line
fixed_lines = []
for i, line in enumerate(lines):
    # Check if line has the corrupted import
    if 'from diff_engine import' in line and '\\n' in line:
        # Split on \n and create proper lines
        parts = line.split('\\n')
        for part in parts:
            if part.strip():
                fixed_lines.append(part + '\n')
    else:
        fixed_lines.append(line)

with open(r'c:\Users\djohn\.aria\src\agent_manager.py', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print("Fixed agent_manager.py")
