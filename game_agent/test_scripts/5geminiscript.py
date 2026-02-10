"""
Combat script: King Slime
Strategy: Matador Style Kiting.
The script employs a two-state movement logic based on King Slime's vertical position.
1. Grounded/Low State: When the boss is near the ground, the player kites horizontally AWAY to maintain safety.
2. Airborne State: When the boss performs his signature high jump, the player reverses direction to run UNDERNEATH him.
   This effectively swaps sides, resetting the arena space and preventing the player from being cornered.
   Dash is used to accelerate these movements when proximity is dangerous.
"""

# Configuration
PLAYER_X = 1280
PLAYER_Y = 720
JUMP_THRESHOLD = 550    # Y coordinate to consider the boss "in the air" (Player is at 720)
SAFE_BUFFER = 400       # Distance to maintain when kiting
DANGER_ZONE = 250       # Distance to trigger evasive dashes

def run(game_state, actions):
    '''Called every frame. React to enemy position.'''
    enemies = game_state.get_found_entities()

    target = None
    for name, entity in enemies.items():
        if "king" in name:
            target = entity
            break
    
    # Fallback to any entity if boss not explicitly found (handling minions/renaming)
    if not target and enemies:
        target = list(enemies.values())[0]
        
    if not target:
        return

    # Enemy Position
    ex = target['x']
    ey = target['y']
    
    # Relative Position
    dx = ex - PLAYER_X
    dist_x = abs(dx)
    
    # Combat: Always attack the boss
    actions.attack_at(ex, ey)

    # Movement Logic
    
    # State 1: The Undercut (Boss is jumping high)
    # If the boss is significantly above the player, we run TOWARDS him to switch sides.
    if ey < JUMP_THRESHOLD:
        if dx < 0:
            # Boss is to the left and high -> Run Left (under him)
            actions.move_left(0.1)
            # Dash if we need to close the gap quickly to get under safely
            if dist_x < 300:
                actions.dash_left()
        else:
            # Boss is to the right and high -> Run Right (under him)
            actions.move_right(0.1)
            if dist_x < 300:
                actions.dash_right()
                
    # State 2: The Kite (Boss is grounded or doing small hops)
    # We run AWAY from the boss to keep distance.
    else:
        if dx < 0:
            # Boss is to the left -> Run Right
            actions.move_right(0.1)
            # If he gets too close, Dash Right to escape
            if dist_x < DANGER_ZONE:
                actions.dash_right()
        else:
            # Boss is to the right -> Run Left
            actions.move_left(0.1)
            # If he gets too close, Dash Left to escape
            if dist_x < DANGER_ZONE:
                actions.dash_left()
                
        # Terrain/Minion hopping: 
        # If we are relatively close, add small jumps to clear ground slime minions
        if dist_x < SAFE_BUFFER:
            actions.jump(0.1)