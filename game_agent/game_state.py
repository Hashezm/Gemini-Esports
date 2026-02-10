"""
Thread-safe shared game state dictionary.
Updated by tracker_service, read by behavior scripts.
"""

import threading
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict


class GameState:
    """Thread-safe game state that holds entity positions."""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._entities: Dict[str, Dict[str, Any]] = {}
        self._player: Dict[str, Any] = {"x": 0, "y": 0}
        self._callbacks = []
    
    def update_entity(self, name: str, x: int, y: int, found: bool = True, **extra):
        """Update an entity's position (called by tracker)."""
        with self._lock:
            self._entities[name] = {
                "x": x,
                "y": y,
                "found": found,
                **extra
            }
    
    def get_entity(self, name: str) -> Optional[Dict[str, Any]]:
        """Get an entity's current state."""
        with self._lock:
            return self._entities.get(name, None)
    
    def get_all_entities(self) -> Dict[str, Dict[str, Any]]:
        """Get all entities."""
        with self._lock:
            return dict(self._entities)
    
    def get_found_entities(self) -> Dict[str, Dict[str, Any]]:
        """Get only entities currently visible on screen."""
        with self._lock:
            return {k: v for k, v in self._entities.items() if v.get("found", False)}
    
    def set_player(self, x: int, y: int, **extra):
        """Update player position."""
        with self._lock:
            self._player = {"x": x, "y": y, **extra}
    
    def get_player(self) -> Dict[str, Any]:
        """Get player position."""
        with self._lock:
            return dict(self._player)
    
    def to_dict(self) -> Dict[str, Any]:
        """Export full state as dictionary."""
        with self._lock:
            return {
                "player": dict(self._player),
                "entities": dict(self._entities)
            }
    
    def __repr__(self):
        return f"GameState({self.to_dict()})"


# Global instance
game_state = GameState()
