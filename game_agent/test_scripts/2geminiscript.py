"""
Combat script: King Slime
Strategy: Aggressive Side-Swapping (The "Passthrough" Method).
Instead of just running away, this script maintains distance until the boss closes the gap.
When King Slime gets too close (within 250px) or is about to land on the player, the script
activates DASH TOWARDS the boss. The dash provides invincibility, allowing the player to 
pass safely through the boss's massive hitbox. Once on the other side, the player runs away 
again to gain distance. This loop prevents cornering.
"""

# Configuration
PLAYER_X = 1280
PLAYER_Y = 720
SWAP_DISTANCE = 250      # Distance to trigger the dash-through maneuver
SAFE_BUFFER = 500        # Distance to try and maintain when running away

def run(game_state, actions):
    '''Called every frame. Uses invincibility dash to cross up the boss.'''
    enemies = game_state.get_found_entities()
    
    # Locate King Slime
    target = None
    for name, entity in enemies.items():
        if "king" in name:
            target = entity
            break
            
    # Fallback to any entity if boss not explicitly named yet (or minions)
    if not target and enemies:
        target = list(enemies.values())[0]
        
    if not target:
        return

    # Target stats
    ex = target['x']
    ey = target['y']
    
    # 1. Always attack the boss
    actions.attack_at(ex, ey)

    # 2. Calculate positioning
    dx = ex - PLAYER_X
    dy = ey - PLAYER_Y
    enemy_is_left = dx < 0
    enemy_is_right = dx > 0
    dist_x = abs(dx)

    # 3. Movement Logic
    
    # EMERGENCY / SWAP PHASE: Enemy is too close or above us
    # We dash TOWARDS the enemy to pass through them using i-frames
    if dist_x < SWAP_DISTANCE:
        if enemy_is_left:
            # Enemy left -> Dash Left (into him) to get to his right side
            actions.dash_left()
            actions.move_left(0.1) 
        else:
            # Enemy right -> Dash Right (into him) to get to his left side
            actions.dash_right()
            actions.move_right(0.1)
            
        # Jump to clear ground minions and ensure we don't snag on the boss's bottom hitbox
        actions.jump(0.1)

    # KITING PHASE: Enemy is at a safe distance
    # Run AWAY from the enemy
    else:
        if enemy_is_left:
            # Enemy is left, run right
            actions.move_right(0.1)
        else:
            # Enemy is right, run left
            actions.move_left(0.1)
            
        # If there's a minion or obstacle in our path (implicit logic), or boss is high up
        # adding small hops helps keep mobility
        if dist_x < SAFE_BUFFER and dy > -100:
            # occasional hops when running to avoid small slimes
            pass # Actually, let's save jump for the swap to avoid air-stalls