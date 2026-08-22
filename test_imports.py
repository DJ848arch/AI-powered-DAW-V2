import sys
sys.path.insert(0, r'c:\Users\djohn\.aria\src')

# Test imports
from diff_engine import Transaction, DiffOperation, DiffOperationType, SongDocument
from lock_manager import LockManager, LockLevel, TransparencyLogEntry
from selection_model import SelectionManager, Selection, SelectionType

print('All v1.1 module imports successful')
