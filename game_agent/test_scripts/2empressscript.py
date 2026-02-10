"""
Combat script: Empress of Light
Strategy: High-speed Runway Kiting with Rapid Vertical Oscillation.
1. Horizontal: Run away from the boss using the infinite platform. Uses a buffer (hysteresis) to prevent loss of speed from turning around too often.
2. Vertical: Faster "Sawtooth" wave pattern. Short bursts of flight followed by falling to disrupt the predictive tracking of the Ethereal Lances.
3. Combat: Rapid-fire clicking logic to maximize the fire rate of the non-automatic weapon.
"""

# Configuration
PLAYER_X = 1280
PLAYER_Y = 720
FLIGHT_CYCLE = 30       # Total frames for one up/down cycle (faster = better dodge for tracking)
DIRECTION_BUFFER = 150  # Pixels of buffer before switching run direction
CLICK_RATE = 4          # Click mouse every N frames

# State variables
frame_count = 0
last_enemy_x = 1280
last_enemy_y = 0
run_direction = -1 # -1 for Left, 1 for Right. Start running Left.

def run(game_state, actions):
    global frame_count, last_enemy_x, last_enemy_y, run_direction
    frame_count += 1
    
    print(f"\n--- Frame {frame_count} ---")

    # --- 1. Target Tracking ---
    entities = game_state.get_found_entities()
    empress_found = False
    for name, entity in entities.items():
        if "empress" in name.lower():
            last_enemy_x = entity["x"]
            last_enemy_y = entity["y"]
            empress_found = True
            print(f"[TRACK] Empress found at ({last_enemy_x}, {last_enemy_y})")
            break
    if not empress_found:
        print(f"[TRACK] Empress NOT found — using last known pos ({last_enemy_x}, {last_enemy_y})")

    # --- 2. Horizontal Movement (Momentum Preserving Kiting) ---
    # Only switch direction if the enemy has clearly crossed the screen to the other side.
    # This prevents us from turning around constantly when she hovers directly above/below.
    
    prev_direction = run_direction
    if last_enemy_x > PLAYER_X + DIRECTION_BUFFER:
        run_direction = -1 # Enemy is Right, Run Left
    elif last_enemy_x < PLAYER_X - DIRECTION_BUFFER:
        run_direction = 1  # Enemy is Left, Run Right
    
    if run_direction != prev_direction:
        print(f"[MOVE] Direction SWITCHED to {'LEFT' if run_direction == -1 else 'RIGHT'}")

    if run_direction == -1:
        actions.move_left()
        actions.dash_left() # Dash aggressively to maintain top speed
        print(f"[MOVE] Running LEFT + Dash LEFT")
    else:
        actions.move_right()
        actions.dash_right()
        print(f"[MOVE] Running RIGHT + Dash RIGHT")

    # --- 3. Vertical Movement (The Micro-Wave) ---
    # Oscillate up and down rapidly. 
    # Frames 0-14: Fly Up
    # Frames 15-29: Fall
    cycle_tick = frame_count % FLIGHT_CYCLE
    
    if cycle_tick < (FLIGHT_CYCLE // 2):
        actions.fly_up()
        print(f"[VERT] Flying UP (cycle tick {cycle_tick}/{FLIGHT_CYCLE})")
    else:
        # Releasing space allows gravity to drop us quickly
        print(f"[VERT] Falling (cycle tick {cycle_tick}/{FLIGHT_CYCLE})")

    # --- 4. Combat Logic (Semi-Auto) ---
    # Pulse the attack command to simulate clicking.
    # We attack for 1 frame, then wait for (CLICK_RATE-1) frames.
    if frame_count % CLICK_RATE == 0:
        actions.attack_at(last_enemy_x, last_enemy_y)
        print(f"[COMBAT] ATTACKING at ({last_enemy_x}, {last_enemy_y})")
    else:
        print(f"[COMBAT] Cooldown ({frame_count % CLICK_RATE}/{CLICK_RATE})")