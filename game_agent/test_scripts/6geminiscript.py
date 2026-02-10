"""
Combat script: King Slime
Strategy: Vertical Gate Kiting.
1. Primary Mode (Ground/Low): When King Slime is on the ground or doing small hops, we run AWAY to maintain distance for ranged attacks. We hop to avoid friction from small slimes.
2. Undercut Mode (High Jump): We only attempt to swap sides when King Slime is at the peak of his high jump (Y < 400). We run TOWARDS him to pass safely underneath.
3. This creates a loop: Kite one way -> He jumps high -> We swap sides -> Kite the other way.
"""

# Configuration
PLAYER_X = 1280
PLAYER_Y = 720
BOSS_HIGH_JUMP_THRESHOLD = 400  # Only run under if he is higher than this (Lower Y = Higher up)
SAFE_DISTANCE = 500             # Maintain this distance for ranged attacks
PANIC_DISTANCE = 200            # If he lands this close, dash away

def run(game_state, actions):
    '''Called every frame. React to enemy position.'''
    enemies = game_state.get_found_entities()

    # Identify target
    target = None
    for name, entity in enemies.items():
        if "king" in name:
            target = entity
            break
            
    # If no specific boss found, target closest entity (minions) to clear them
    if not target and enemies:
        target = list(enemies.values())[0]
        
    if not target:
        return

    enemy_x = target['x']
    enemy_y = target['y']
    
    # Calculate relative position
    dx = enemy_x - PLAYER_X
    dist_x = abs(dx)
    
    enemy_is_left = dx < 0
    enemy_is_right = dx > 0

    # 1. Combat: Always attack the boss
    actions.attack_at(enemy_x, enemy_y)

    # 2. Movement Logic
    
    # CASE A: Boss is High in the Air (The Undercut)
    # He is high enough to safely run underneath to swap sides/reset arena.
    if enemy_y < BOSS_HIGH_JUMP_THRESHOLD:
        if enemy_is_left:
            actions.move_left(0.1) # Run towards him (Left)
            actions.dash_left()    # Dash to ensure we clear the gap quickly
        else:
            actions.move_right(0.1) # Run towards him (Right)
            actions.dash_right()    # Dash to ensure we clear the gap quickly
            
    # CASE B: Boss is Grounded or Low Hop (The Kite)
    # Run away to keep safe distance.
    else:
        if enemy_is_left:
            actions.move_right(0.1) # Run away (Right)
            # If he lands too close, panic dash away
            if dist_x < PANIC_DISTANCE:
                actions.dash_right()
        else:
            actions.move_left(0.1)  # Run away (Left)
            # If he lands too close, panic dash away
            if dist_x < PANIC_DISTANCE:
                actions.dash_left()
                
        # Bunny Hop Logic
        # Jump periodically to maintain speed and avoid small slimes on the floor
        if dist_x < SAFE_DISTANCE:
             actions.jump(0.1)

    # 3. Anti-Stuck / Minion Clearing
    # If we are surrounded by entities (boss or minions), simple jump helps escape hitbox friction
    if dist_x < 100:
        actions.jump(0.1)