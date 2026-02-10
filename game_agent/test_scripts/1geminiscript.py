"""
Combat script: King Slime
Strategy: Horizontal kiting. King Slime primarily moves by hopping towards the player and deals contact damage.
The strategy is to maintain a safe distance by constantly running away from the boss's direction.
If the boss closes the gap (Danger Distance), the script uses Dash to utilize invincibility frames and quickly create space.
The player attacks continuously towards the boss's coordinates.
"""

# Configuration
PLAYER_X = 1280  # Player always at screen center
PLAYER_Y = 720
SAFE_DISTANCE = 450  # Distance to maintain to allow reaction time
DANGER_DISTANCE = 250  # Distance to trigger dashes
CRITICAL_DISTANCE = 100 # Distance to trigger panic jumps

def run(game_state, actions):
    '''Called every frame. React to enemy position.'''
    enemies = game_state.get_found_entities()

    # Identify target (King Slime)
    target = None
    for name, entity in enemies.items():
        # Look for the boss, or default to first entity found
        if "king" in name or "slime" in name:
            target = entity
            break
    
    # If no enemies found, do nothing
    if not target:
        return

    # Extract enemy coordinates
    enemy_x = target['x']
    enemy_y = target['y']
    
    # ---------------------------------------------------------
    # 1. Combat Logic: Constant Aggression
    # ---------------------------------------------------------
    actions.attack_at(enemy_x, enemy_y)

    # ---------------------------------------------------------
    # 2. Movement Logic: Kiting and Evasion
    # ---------------------------------------------------------
    dx = enemy_x - PLAYER_X
    abs_dist = abs(dx)
    
    # Determine if enemy is to the left or right
    enemy_is_left = dx < 0

    if abs_dist < DANGER_DISTANCE:
        # Case A: Enemy is dangerously close. Use Dash to escape.
        if enemy_is_left:
            actions.dash_right()
            actions.move_right(0.1)
        else:
            actions.dash_left()
            actions.move_left(0.1)
            
        # If very close, add a jump to avoid ground hitbox or smaller slimes
        if abs_dist < CRITICAL_DISTANCE:
            actions.jump(0.2) 

    elif abs_dist < SAFE_DISTANCE:
        # Case B: Enemy is within visual range but not immediate danger. Run away.
        if enemy_is_left:
            actions.move_right(0.1)
        else:
            actions.move_left(0.1)
            
    # ---------------------------------------------------------
    # 3. Vertical Awareness (Anti-Stomp)
    # ---------------------------------------------------------
    # If King Slime is significantly above the player (jumping), ensure we aren't under him.
    # Note: Y decreases as you go up.
    if enemy_y < PLAYER_Y - 150 and abs_dist < 150:
        if enemy_is_left:
            actions.dash_right()
        else:
            actions.dash_left()