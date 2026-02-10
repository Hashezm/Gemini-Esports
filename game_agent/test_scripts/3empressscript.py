"""
Combat script: Empress of Light
Strategy: Anti-Gravity Kiting.
1. Horizontal: Maintain maximum distance. Only turn around if the boss fully crosses to the other side.
2. Vertical: "Shark-fin" pattern. Short burst of flight to dodge, followed by an EXTENDED, FORCED FAST-FALL to combat low gravity and prevent floating into space.
3. Action: Uses `move_down()` aggressively to ensure we stay near the platform level.
"""

# Configuration
PLAYER_X = 1280
PLAYER_Y = 720
CLICK_RATE = 4         # Fire weapon every 4 frames

# Vertical Cycle Config
# We want a cycle that favors going down to counter the "float" into space.
CYCLE_LENGTH = 45      # Total duration of one wave
UP_PHASE = 12          # Fly up for only 12 frames
# Down phase is the remaining 33 frames, where we will fast-fall.

# Movement State
frame_count = 0
run_direction = -1     # Start running left
last_enemy_x = 1280
last_enemy_y = 0

def run(game_state, actions):
    global frame_count, run_direction, last_enemy_x, last_enemy_y
    frame_count += 1
    
    print(f"\n--- Frame {frame_count} ---")

    # --- 1. Target Tracking ---
    entities = game_state.get_found_entities()
    boss_found = False
    
    for name, entity in entities.items():
        if "empress" in name.lower():
            last_enemy_x = entity["x"]
            last_enemy_y = entity["y"]
            boss_found = True
            print(f"[TRACK] Empress found at ({last_enemy_x}, {last_enemy_y})")
            break
    if not boss_found:
        print(f"[TRACK] Empress NOT found — using last known pos ({last_enemy_x}, {last_enemy_y})")
            
    # --- 2. Horizontal Kiting (Hysteresis) ---
    # Don't switch directions instantly to preserve speed.
    # Buffer of 200 pixels prevents jittering when she is directly above.
    buffer = 200
    
    prev_direction = run_direction
    if last_enemy_x > PLAYER_X + buffer:
        run_direction = -1 # Run Left
    elif last_enemy_x < PLAYER_X - buffer:
        run_direction = 1  # Run Right
    
    if run_direction != prev_direction:
        print(f"[MOVE] Direction SWITCHED to {'LEFT' if run_direction == -1 else 'RIGHT'}")

    if run_direction == -1:
        actions.move_left()
        actions.dash_left()
        print(f"[MOVE] Running LEFT + Dash LEFT")
    else:
        actions.move_right()
        actions.dash_right()
        print(f"[MOVE] Running RIGHT + Dash RIGHT")

    # --- 3. Vertical Logic (Anti-Space Drift) ---
    # Calculate where we are in the wave pattern
    cycle_tick = frame_count % CYCLE_LENGTH
    
    if cycle_tick < UP_PHASE:
        # Phase 1: Short burst up to dodge lances
        actions.fly_up()
        print(f"[VERT] Flying UP (cycle tick {cycle_tick}/{CYCLE_LENGTH})")
    else:
        # Phase 2: Long, aggressive descent
        # Holding 'down' (S key) increases fall speed significantly,
        # which is required to escape the low gravity of the Space layer.
        actions.move_down()
        print(f"[VERT] FAST-FALLING down (cycle tick {cycle_tick}/{CYCLE_LENGTH})")

    # --- 4. Combat Logic ---
    # Pulse fire the weapon
    if frame_count % CLICK_RATE == 0:
        actions.attack_at(last_enemy_x, last_enemy_y)
        print(f"[COMBAT] ATTACKING at ({last_enemy_x}, {last_enemy_y})")
    else:
        print(f"[COMBAT] Cooldown ({frame_count % CLICK_RATE}/{CLICK_RATE})")