"""
Non-blocking game action system using pydirectinput.

Design: Scripts declare INTENT each frame (e.g. "I want to move left and attack").
The script_runner calls flush() once per frame to reconcile intent with actual inputs.
No time.sleep() inside any script-facing method — all actions are instant.
"""

import pydirectinput
import time
from typing import Optional, Tuple


# Minimal pause between pydirectinput calls — just enough for the OS to register inputs
pydirectinput.PAUSE = 0.005


class Actions:
    """
    Non-blocking action system for behavior scripts.
    
    Scripts call methods like move_left() and attack_at(x, y) to declare
    what they want to happen THIS frame. Nothing actually executes until
    flush() is called by the script runner after run() returns.
    
    This means scripts can call as many actions as they want per frame
    with zero performance penalty — the engine handles it all in one pass.
    """
    
    def __init__(self):
        # --- Persistent state (survives across frames) ---
        self._held_keys: set = set()       # Keys currently physically held down
        self._mouse_is_down: bool = False  # Whether mouse button is currently held
        
        # --- Per-frame intent (reset after every flush) ---
        self._desired_keys: set = set()             # Keys the script wants held this frame
        self._mouse_target: Optional[Tuple[int, int]] = None  # Where to aim (x, y)
        self._want_attack: bool = False              # Whether to hold mouse button
        self._queued_dashes: list = []               # Queued dash directions ('left'/'right')
    
    # =========================================================
    # MOVEMENT — Call these to hold a direction key this frame
    # =========================================================
    
    def move_left(self):
        """Hold the left movement key (A) this frame."""
        self._desired_keys.add('a')
    
    def move_right(self):
        """Hold the right movement key (D) this frame."""
        self._desired_keys.add('d')
    
    def fly_up(self):
        """Hold the fly/jump key (Space) this frame."""
        self._desired_keys.add('space')
    
    def move_down(self):
        """Hold the down key (S) this frame."""
        self._desired_keys.add('s')
    
    def move_down_fast(self):
        """Hold the fast-fall key (B) this frame."""
        self._desired_keys.add('b')
    
    # =========================================================
    # COMBAT — Aim and hold attack this frame
    # =========================================================
    
    def attack_at(self, x: int, y: int):
        """Aim at a screen position and hold attack this frame.
        
        Call this every frame you want to keep shooting. The mouse moves
        to (x, y) and the left mouse button is held. When you stop calling
        this, the mouse button is automatically released next frame.
        """
        self._mouse_target = (int(x), int(y))
        self._want_attack = True
    
    # =========================================================
    # DASHES — One-shot actions, queued for this frame
    # =========================================================
    
    def dash_left(self):
        """Queue a dash left (double-tap A). Only one dash executes per frame."""
        self._queued_dashes.append('left')
    
    def dash_right(self):
        """Queue a dash right (double-tap D). Only one dash executes per frame."""
        self._queued_dashes.append('right')
    
    # =========================================================
    # ENGINE METHODS — Called by script_runner, NOT by scripts
    # =========================================================
    
    def flush(self):
        """
        Apply all frame intents as actual game inputs.
        Called once per frame by script_runner AFTER run() returns.
        
        Order of operations:
        1. Execute queued dashes (only blocking operation, ~55ms)
        2. Reconcile held keys with desired keys (press new, release old)
        3. Move mouse to target
        4. Handle mouse button (attack) state
        5. Clear per-frame intent
        """
        
        # 1. Execute queued dashes (at most one per frame)
        #    Dashes require a double-tap, which needs a small blocking gap.
        #    This is the ONLY blocking operation in the entire system.
        if self._queued_dashes:
            direction = self._queued_dashes[0]  # Only first dash per frame
            key = 'a' if direction == 'left' else 'd'
            
            # Release the key first if it's currently held (double-tap won't register otherwise)
            if key in self._held_keys:
                pydirectinput.keyUp(key)
                self._held_keys.discard(key)
            
            # Double-tap: press, brief gap, press
            pydirectinput.press(key)
            time.sleep(0.03)  # Minimal gap for game to register as double-tap
            pydirectinput.press(key)
            # After press(), the key is released — reconciliation below will
            # re-press it if the script also wants to move in that direction.
        
        # 2. Reconcile movement keys
        #    Release keys no longer wanted, press newly wanted keys.
        keys_to_release = self._held_keys - self._desired_keys
        keys_to_press = self._desired_keys - self._held_keys
        
        for key in keys_to_release:
            pydirectinput.keyUp(key)
        for key in keys_to_press:
            pydirectinput.keyDown(key)
        
        # Update held state to match desired
        self._held_keys = set(self._desired_keys)
        
        # 3. Move mouse to target position
        if self._mouse_target:
            pydirectinput.moveTo(self._mouse_target[0], self._mouse_target[1])
        
        # 4. Handle mouse button state (attack)
        if self._want_attack and not self._mouse_is_down:
            pydirectinput.mouseDown()
            self._mouse_is_down = True
        elif not self._want_attack and self._mouse_is_down:
            pydirectinput.mouseUp()
            self._mouse_is_down = False
        
        # 5. Reset per-frame intent for next frame
        self._desired_keys.clear()
        self._mouse_target = None
        self._want_attack = False
        self._queued_dashes.clear()
    
    def release_all(self):
        """Release all held keys and mouse button. Called on shutdown."""
        for key in self._held_keys:
            pydirectinput.keyUp(key)
        if self._mouse_is_down:
            pydirectinput.mouseUp()
            self._mouse_is_down = False
        self._held_keys.clear()


# Global instance
actions = Actions()
