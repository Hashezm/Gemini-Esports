"""
Combat script: King Slime
Strategy: Kite and Switch.
1. Primary Goal: Maintain horizontal distance (Kiting) by running away.
2. Undercut: Only if King Slime is VERY high in the air (High Jump), dash/run underneath him to swap sides and reset arena space.
3. Panic Escape: If he is on the ground and too close, use verticality (Jump/Double Jump) to go OVER him rather than trying to outrun him on the ground if cornered.
"""

# Configuration
PLAYER_X = 1280
PLAYER_Y = 720
UNDERCUT_Y_THRESHOLD = 350  # Boss must be this high (low Y value) to attempt running under. 
                            # Player is at 720, so 350 is significantly above.
SAFE_DISTANCE = 450         # Ideal distance
PANIC_DISTANCE = 180        # Too close!

def run(game_state, actions):
    '''Called every frame. React to enemy position.'''
    enemies = game_state.get_found_entities()

    # Identify target
    target = None
    for name, entity in enemies.items():
        if "king" in name:
            target = entity
            break
    
    # Fallback
    if not target and enemies:
        target = list(enemies.values())[0]
        
    if not target:
        return

    # Target info
    ex = target['x']
    ey = target['y']
    
    dx = ex - PLAYER_X
    dy = ey - PLAYER_Y
    dist_x = abs(dx)
    
    # Always attack the boss
    actions.attack_at(ex, ey)

    # LOGIC TREE

    # 1. UNDERCUT MANEUVER (Only on High Jumps)
    # If the boss is high enough, we take the opportunity to switch sides.
    # This resets our kiting room.
    if ey < UNDERCUT_Y_THRESHOLD:
        if dx < 0: 
            # Boss is left and high -> Run Left (under him)
            actions.move_left(0.1)
            actions.dash_left()
        else: 
            # Boss is right and high -> Run Right (under him)
            actions.move_right(0.1)
            actions.dash_right()
            
    # 2. STANDARD KITING (Boss is low/grounded)
    else:
        # Move AWAY from the boss
        if dx < 0: # Boss is left
            actions.move_right(0.1)
            # Panic logic: If he's close on the ground
            if dist_x < PANIC_DISTANCE:
                # Jump to try and clear him or minions
                actions.jump(0.5) 
                # If VERY close, try to dash away to gain gap
                actions.dash_right()
        else: # Boss is right
            actions.move_left(0.1)
            # Panic logic
            if dist_x < PANIC_DISTANCE:
                actions.jump(0.5)
                actions.dash_left()

        # 3. MINION HOP
        # If we are just running and there are likely minions (boss is somewhat close),
        # do small hops to avoid getting slowed by slime contact on the floor.
        if dist_x < SAFE_DISTANCE and dist_x > PANIC_DISTANCE:
            # Random small jumps or timed jumps can help, 
            # here we just tap jump occasionally if on ground (simulated by not holding it long)
            # We can't check 'if on ground' easily, so we just pulse jump lightly.
            # However, spamming jump slows running speed in Terraria, so use sparingly.
            pass

    # 4. ANTI-STUCK
    # If the boss teleports (sudden change in position not matching velocity), 
    # the logic naturally updates next frame.
    # The most dangerous moment is the teleport onto the player. 
    # If boss is literally ON TOP of player (dx very small, dy very small), DASH immediately.
    if dist_x < 50 and abs(dy) < 100:
        if dx < 0: actions.dash_right()
        else: actions.dash_left()