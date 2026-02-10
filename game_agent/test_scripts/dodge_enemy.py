"""
Example behavior script: Dodge when enemy is close.

This script demonstrates how to react to entity positions.
The `run` function is called every frame by script_runner.py.
All action calls are non-blocking — they declare intent for this frame only.
"""


# Configuration
DODGE_DISTANCE = 300  # Dodge when enemy is within this many pixels
SCREEN_CENTER_X = 1280  # Half of 2560 resolution


def run(game_state, actions):
    """
    Called every frame by script_runner.
    
    Args:
        game_state: GameState object with entity positions
        actions: Actions object — call methods to declare intent for this frame
    """
    # Get all visible entities
    entities = game_state.get_found_entities()
    
    if not entities:
        return  # Nothing to dodge
    
    # Check each entity
    for name, entity in entities.items():
        x, y = entity["x"], entity["y"]
        
        # Simple dodge logic: if enemy is on left, move right (and vice versa)
        if x < SCREEN_CENTER_X:
            actions.move_right()
        else:
            actions.move_left()
        
        # Always shoot at the enemy while dodging
        actions.attack_at(x, y)
        
        # Only react to first entity found
        break
