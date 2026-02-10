"""
Combat script: King Slime
Strategy: Dynamic Kiting with Vertical Undercut.
We mainly kite the boss horizontally to maintain distance. However, to avoid running out of arena space,
we watch for King Slime's high jumps. When he is significantly above the player (Y coordinate check),
we reverse direction and dash/run underneath him. This safely swaps our relative position.
We also use the dash ability to create gaps if he gets too close on the ground.
"""

# Configuration
PLAYER_X = 1280
PLAYER_Y = 720
# Threshold to consider the boss "High enough to run under"
# We want his center to be high enough that we don't touch his bottom hitbox.
UNDERCUT_Y_THRESHOLD = 500 
SAFE_DISTANCE = 400
DANGER_DISTANCE = 250

def run(game_state, actions):
    '''Called every frame. React to enemy position.'''
    enemies = game_state.get_found_entities()

    # Identify target
    target = None
    for name, entity in enemies.items():
        if "king" in name:
            target = entity
            break
    
    # Fallback if specific name not found yet
    if not target and enemies:
        target = list(enemies.values())[0]
        
    if not target:
        return

    enemy_x = target['x']
    enemy_y = target['y']
    
    # Always attack towards the boss
    actions.attack_at(enemy_x, enemy_y)

    dx = enemy_x - PLAYER_X
    dist_x = abs(dx)
    
    # Logic Decision Tree
    
    # 1. UNDERCUT OPPORTUNITY: Boss is high in the air.
    # We move TOWARDS the boss to switch sides safely.
    if enemy_y < UNDERCUT_Y_THRESHOLD:
        if dx < 0: # Boss is left, high up
            actions.move_left(0.1) # Run left (under him)
            actions.dash_left()    # Dash for speed/safety
        else:      # Boss is right, high up
            actions.move_right(0.1) # Run right (under him)
            actions.dash_right()    # Dash for speed/safety
            
    # 2. STANDARD KITING: Boss is low/grounded.
    # We run AWAY from the boss.
    else:
        if dx < 0: # Boss is left
            actions.move_right(0.1) # Run right
            
            # If he gets too close, panic dash away
            if dist_x < DANGER_DISTANCE:
                actions.dash_right()
                
        else: # Boss is right
            actions.move_left(0.1) # Run left
            
            # If he gets too close, panic dash away
            if dist_x < DANGER_DISTANCE:
                actions.dash_left()
        
        # 3. MINION/TERRAIN MANAGEMENT
        # Perform short hops while running to avoid the small slimes he spawns
        # and to maintain momentum over uneven terrain.
        if dist_x < SAFE_DISTANCE:
            actions.jump(0.1)