"""
Combat script: Empress of Light
Strategy: High-mobility Run-and-Gun.
1. Kiting: Move horizontally away from the boss at all times to outspace attacks.
2. Speed: Spam dash actions constantly to maintain maximum velocity on the infinite platform.
3. Verticality: Oscillate height (fly/fall) to dodge predictive lance attacks and ground hazards.
4. Offense: Pulse-fire the homing weapon at the last known enemy position.
"""

# Configuration
PLAYER_X = 1280
PLAYER_Y = 720

# State variables
last_enemy_x = 1280  # Default to center
last_enemy_y = 400   # Default to above center
frame_count = 0

def run(game_state, actions):
    global last_enemy_x, last_enemy_y, frame_count
    frame_count += 1
    
    # --- 1. Target Tracking ---
    entities = game_state.get_found_entities()
    target_visible = False
    
    for name, entity in entities.items():
        if "empress" in name.lower():
            last_enemy_x = entity["x"]
            last_enemy_y = entity["y"]
            target_visible = True
            break
            
    # --- 2. Movement Logic ---
    # Strategy: Maintain maximum horizontal distance.
    # If the enemy is to our right, we run/dash left.
    # If the enemy is to our left, we run/dash right.
    
    is_enemy_to_right = last_enemy_x > PLAYER_X
    
    if is_enemy_to_right:
        actions.move_left()
        actions.dash_left()  # Request dash every frame; engine handles cooldown
    else:
        actions.move_right()
        actions.dash_right()
        
    # Vertical Evasion:
    # The Empress has horizontal sweeping attacks (Lances). 
    # Moving in a "Sawtooth" or "Sine" wave pattern (Up/Down) breaks their tracking.
    # We use a timer to alternate between flying up and falling.
    # 20 frames (~0.6s) up, 20 frames down.
    if (frame_count // 20) % 2 == 0:
        actions.fly_up()
        
    # --- 3. Combat Logic ---
    # The prompt specifies the gun needs to be repeatedly clicked.
    # We pulse the attack command every few frames to simulate clicks.
    # Homing bullets handle the accuracy.
    
    if frame_count % 3 == 0:
        actions.attack_at(last_enemy_x, last_enemy_y)