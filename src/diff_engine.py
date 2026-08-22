"""
Diff Engine - Core diff-based mutation system for v1.1 Architecture
Provides surgical JSON updates instead of full overwrites
"""

import json
import copy
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime
import threading
from PyQt6.QtCore import QObject, pyqtSignal


class DiffOperationType(Enum):
    ADD = "add"
    REMOVE = "remove"
    REPLACE = "replace"
    MOVE = "move"
    COPY = "copy"


@dataclass
class DiffOperation:
    """Single diff operation representing a change to the document"""
    path: str  # JSON Pointer path (e.g., "/tracks/0/clips/1")
    operation: DiffOperationType
    value: Any = None
    old_value: Any = None  # For undo/redo
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "path": self.path,
            "operation": self.operation.value,
            "value": self.value,
            "old_value": self.old_value,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'DiffOperation':
        return cls(
            path=data["path"],
            operation=DiffOperationType(data["operation"]),
            value=data.get("value"),
            old_value=data.get("old_value"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            metadata=data.get("metadata", {})
        )
    
    def inverse(self) -> 'DiffOperation':
        """Create inverse operation for undo"""
        if self.operation == DiffOperationType.ADD:
            return DiffOperation(
                path=self.path,
                operation=DiffOperationType.REMOVE,
                value=self.old_value,
                old_value=self.value
            )
        elif self.operation == DiffOperationType.REMOVE:
            return DiffOperation(
                path=self.path,
                operation=DiffOperationType.ADD,
                value=self.old_value,
                old_value=self.value
            )
        elif self.operation == DiffOperationType.REPLACE:
            return DiffOperation(
                path=self.path,
                operation=DiffOperationType.REPLACE,
                value=self.old_value,
                old_value=self.value
            )
        return self


@dataclass
class Transaction:
    """Collection of diff operations applied atomically"""
    id: str
    operations: List[DiffOperation] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = ""  # Agent ID or user action
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_operation(self, op: DiffOperation):
        self.operations.append(op)
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "operations": [op.to_dict() for op in self.operations],
            "timestamp": self.timestamp,
            "source": self.source,
            "description": self.description,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Transaction':
        tx = cls(
            id=data["id"],
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            source=data.get("source", ""),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )
        tx.operations = [DiffOperation.from_dict(op) for op in data.get("operations", [])]
        return tx


class ShadowCopy:
    """Lock-free shadow copy for real-time audio thread access"""
    
    def __init__(self, document: Dict):
        self._document = copy.deepcopy(document)
        self._lock = threading.RLock()
        self._version = 0
        self._midi_buffers: Dict[str, Any] = {}
        
    def update(self, new_document: Dict):
        """Update shadow copy with new document state"""
        with self._lock:
            self._document = copy.deepcopy(new_document)
            self._version += 1
    
    def get(self) -> Dict:
        """Get read-only copy of document"""
        with self._lock:
            return copy.deepcopy(self._document)
    
    def get_version(self) -> int:
        return self._version
    
    def get_midi_buffer(self, track_id: str) -> Optional[Any]:
        """Get MIDI buffer for real-time thread"""
        return self._midi_buffers.get(track_id)
    
    def set_midi_buffer(self, track_id: str, buffer: Any):
        """Set MIDI buffer for real-time thread"""
        self._midi_buffers[track_id] = buffer


class UndoManager:
    """Manages undo/redo with inverse diff storage"""
    
    def __init__(self, max_history: int = 100):
        self._undo_stack: List[Transaction] = []
        self._redo_stack: List[Transaction] = []
        self._max_history = max_history
        
    def push(self, transaction: Transaction):
        """Push transaction to undo stack"""
        self._undo_stack.append(transaction)
        self._redo_stack.clear()  # Clear redo on new action
        
        # Limit history size
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)
    
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0
    
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0
    
    def undo(self) -> Optional[Transaction]:
        """Get inverse transaction for undo"""
        if not self._undo_stack:
            return None
        
        transaction = self._undo_stack.pop()
        
        # Create inverse transaction
        inverse_tx = Transaction(
            id=f"undo_{transaction.id}",
            source="undo_manager",
            description=f"Undo: {transaction.description}"
        )
        
        # Reverse operations and invert each
        for op in reversed(transaction.operations):
            inverse_tx.add_operation(op.inverse())
        
        self._redo_stack.append(transaction)
        return inverse_tx
    
    def redo(self) -> Optional[Transaction]:
        """Get transaction for redo"""
        if not self._redo_stack:
            return None
        
        transaction = self._redo_stack.pop()
        self._undo_stack.append(transaction)
        return transaction
    
    def get_history(self) -> List[Transaction]:
        """Get undo history for display"""
        return list(self._undo_stack)
    
    def clear(self):
        """Clear all history"""
        self._undo_stack.clear()
        self._redo_stack.clear()


class SongDocument(QObject):
    """Document that applies transactions atomically"""
    
    # Signals
    document_changed = pyqtSignal(str, list)  # transaction_id, affected_paths
    transaction_applied = pyqtSignal(str)  # transaction_id
    transaction_failed = pyqtSignal(str, str)  # transaction_id, error
    
    def __init__(self, initial_data: Dict = None):
        super().__init__()
        self._data = initial_data or {}
        self._undo_manager = UndoManager()
        self._shadow = ShadowCopy(self._data)
        self._listeners: List[Callable] = []
        self._transaction_log: List[Transaction] = []
        
    def get_data(self) -> Dict:
        """Get current document data"""
        return copy.deepcopy(self._data)
    
    def get_shadow(self) -> ShadowCopy:
        """Get shadow copy for audio thread"""
        return self._shadow
    
    def apply_transaction(self, transaction: Transaction, 
                          validation_callback: Callable = None) -> bool:
        """Apply transaction atomically"""
        try:
            # Validate if callback provided
            if validation_callback and not validation_callback(transaction):
                self.transaction_failed.emit(transaction.id, "Validation failed")
                return False
            
            # Apply each operation
            affected_paths = []
            for op in transaction.operations:
                self._apply_operation(op)
                affected_paths.append(op.path)
            
            # Update shadow copy
            self._shadow.update(self._data)
            
            # Add to undo manager
            self._undo_manager.push(transaction)
            self._transaction_log.append(transaction)
            
            # Notify listeners
            self.document_changed.emit(transaction.id, affected_paths)
            self.transaction_applied.emit(transaction.id)
            
            return True
            
        except Exception as e:
            self.transaction_failed.emit(transaction.id, str(e))
            return False
    
    def _apply_operation(self, op: DiffOperation):
        """Apply single diff operation to document"""
        path_parts = self._parse_path(op.path)
        
        if op.operation == DiffOperationType.ADD:
            self._set_value_at_path(self._data, path_parts, op.value, create_parents=True)
        elif op.operation == DiffOperationType.REMOVE:
            self._remove_value_at_path(self._data, path_parts)
        elif op.operation == DiffOperationType.REPLACE:
            old = self._get_value_at_path(self._data, path_parts)
            op.old_value = old
            self._set_value_at_path(self._data, path_parts, op.value)
    
    def _parse_path(self, path: str) -> List[str]:
        """Parse JSON Pointer path"""
        if path.startswith('/'):
            path = path[1:]
        if not path:
            return []
        return path.split('/')
    
    def _get_value_at_path(self, data: Dict, path_parts: List[str]) -> Any:
        """Get value at path"""
        current = data
        for part in path_parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                idx = int(part)
                current = current[idx] if 0 <= idx < len(current) else None
            else:
                return None
        return current
    
    def _set_value_at_path(self, data: Dict, path_parts: List[str], 
                           value: Any, create_parents: bool = False):
        """Set value at path"""
        current = data
        for i, part in enumerate(path_parts[:-1]):
            if isinstance(current, dict):
                if part not in current and create_parents:
                    # Determine if next part is array index
                    next_part = path_parts[i + 1] if i + 1 < len(path_parts) else None
                    current[part] = [] if next_part and next_part.isdigit() else {}
                current = current.get(part)
            elif isinstance(current, list):
                idx = int(part)
                if idx >= len(current) and create_parents:
                    current.extend([None] * (idx - len(current) + 1))
                current = current[idx] if 0 <= idx < len(current) else None
        
        if path_parts:
            last = path_parts[-1]
            if isinstance(current, dict):
                current[last] = value
            elif isinstance(current, list):
                idx = int(last)
                if idx >= len(current):
                    current.extend([None] * (idx - len(current) + 1))
                current[idx] = value
    
    def _remove_value_at_path(self, data: Dict, path_parts: List[str]):
        """Remove value at path"""
        current = data
        for part in path_parts[:-1]:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                idx = int(part)
                current = current[idx] if 0 <= idx < len(current) else None
        
        if path_parts and current is not None:
            last = path_parts[-1]
            if isinstance(current, dict) and last in current:
                del current[last]
            elif isinstance(current, list):
                idx = int(last)
                if 0 <= idx < len(current):
                    del current[idx]
    
    def undo(self) -> bool:
        """Undo last transaction"""
        inverse_tx = self._undo_manager.undo()
        if inverse_tx:
            return self.apply_transaction(inverse_tx)
        return False
    
    def redo(self) -> bool:
        """Redo last undone transaction"""
        transaction = self._undo_manager.redo()
        if transaction:
            return self.apply_transaction(transaction)
        return False
    
    def can_undo(self) -> bool:
        return self._undo_manager.can_undo()
    
    def can_redo(self) -> bool:
        return self._undo_manager.can_redo()
    
    def get_transaction_log(self) -> List[Transaction]:
        """Get full transaction log"""
        return list(self._transaction_log)
    
    def create_diff(self, old_data: Dict, new_data: Dict, 
                    path_prefix: str = "") -> List[DiffOperation]:
        """Create diff operations between two documents"""
        operations = []
        self._diff_recursive(old_data, new_data, path_prefix, operations)
        return operations
    
    def _diff_recursive(self, old: Any, new: Any, path: str, 
                        operations: List[DiffOperation]):
        """Recursively compute diff"""
        if old == new:
            return
        
        if type(old) != type(new):
            operations.append(DiffOperation(
                path=path,
                operation=DiffOperationType.REPLACE,
                value=new,
                old_value=old
            ))
            return
        
        if isinstance(old, dict):
            all_keys = set(old.keys()) | set(new.keys())
            for key in all_keys:
                child_path = f"{path}/{key}" if path else f"/{key}"
                if key in old and key not in new:
                    operations.append(DiffOperation(
                        path=child_path,
                        operation=DiffOperationType.REMOVE,
                        old_value=old[key]
                    ))
                elif key not in old and key in new:
                    operations.append(DiffOperation(
                        path=child_path,
                        operation=DiffOperationType.ADD,
                        value=new[key]
                    ))
                else:
                    self._diff_recursive(old[key], new[key], child_path, operations)
        
        elif isinstance(old, list):
            max_len = max(len(old), len(new))
            for i in range(max_len):
                child_path = f"{path}/{i}"
                if i < len(old) and i >= len(new):
                    operations.append(DiffOperation(
                        path=child_path,
                        operation=DiffOperationType.REMOVE,
                        old_value=old[i]
                    ))
                elif i >= len(old) and i < len(new):
                    operations.append(DiffOperation(
                        path=child_path,
                        operation=DiffOperationType.ADD,
                        value=new[i]
                    ))
                else:
                    self._diff_recursive(old[i], new[i], child_path, operations)
        
        else:
            operations.append(DiffOperation(
                path=path,
                operation=DiffOperationType.REPLACE,
                value=new,
                old_value=old
            ))
