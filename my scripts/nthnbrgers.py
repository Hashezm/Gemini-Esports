# def function_time(message, client, chat):
#     start_time = time.time()
#     i = 0
#     for chunk in chat.send_message_stream(message):
#         if i == 0:
#             end_time = time.time()
#             delay_ms = (end_time - start_time) * 1000
#             print(f"\n[Response delay: {delay_ms:.2f}ms]")
#             i += 1
#         print(chunk.text)
#     print(f"\n[FULL Response delay: {(time.time() - start_time) * 1000:.2f}ms]")

# # Send a message and stream the response


# function_time('Tell me a short story.', client, chat)
# function_time('Tell me who you are', client, chat)
# function_time('Tell me the meaning of life', client, chat)
# function_time("Summarize our conversation", client, chat)


# This is the actual function that would be called based on the model's suggestion

############-----------------------#######################
# this would listen to keyboard and mouse inputs

# from pynput import keyboard, mouse

# def on_press(key):
#     print(f'Key pressed: {key}')
#     if key == keyboard.Key.esc:
#         # Stop both listeners
#         keyboard_listener.stop()
#         mouse_listener.stop()
#         return False

# def on_move(x, y):
#     print(f'Mouse moved to {x}, {y}')

# keyboard_listener = keyboard.Listener(on_press=on_press)
# mouse_listener = mouse.Listener(on_move=on_move)

# keyboard_listener.start()
# mouse_listener.start()

# keyboard_listener.join()
# mouse_listener.join()

# SYSTEM_INSTRUCTION = """
# You are an autonomous game-playing AI agent. Your task is to execute the actions provided to you using the visual feedback you are receiving through image/video feed, tools provided to you and this prompt.


# CONTROLS:
# - Left click to click
# - Move mouse around to move mouse around


# SCREEN & VISION DATA:
# - You are receiving a video feed at 768x432.
# - **COORDINATE SYSTEM:**
#   - When you use tools, provide coordinates based on the 768x432 image you see.
#   - (0,0) is Top-Left. (767, 431) is Bottom-Right.
#   - The system will automatically scale your inputs up to the real resolution.
#   - DO NOT try to do the math yourself. Just click where you see the object in the 768x768 grid.
#   - the CURSOR indicating where you're clicking is a RED DOT on screen

# Actions to Execute:
#     1. Create a world with default settings
#     2. then you are done!

# IMPORTANT RULES:
# - the CURSOR indicating where you're clicking is a RED DOT on screen
# - You can ONLY use the video feed, this prompt and your tools to understand and progress.
# - When you need to continue or are ready for the next action, take it. Be proactive and keep trying to progress.
# - After EVERY tool call, observe the visual screen update before taking another action. 
# - You must either complete the actions to execute provided to you, or determine that you cannot complete those actions. After that point you should stop and send a message back summarizing what you tried and what occured.
# """

import asyncio
import pyautogui
import pydirectinput
# CALCULATION CONSTANTS
REAL_WIDTH = 2560
REAL_HEIGHT = 1440
MODEL_WIDTH = 768
MODEL_HEIGHT = 432

# X scale: ~3.33, Y scale: ~1.875
X_SCALE = REAL_WIDTH / MODEL_WIDTH
Y_SCALE = REAL_HEIGHT / MODEL_HEIGHT

def move_mouse_relative_to_current_position(dx: int, dy: int) -> str:
    """Move the mouse cursor relative to its current position.
    
    Args:
        dx: Horizontal pixels to move (positive = right, negative = left)
        dy: Vertical pixels to move (positive = down, negative = up)
    """
    scaled_dx = int(dx)
    scaled_dy = int(dy)
    
    pyautogui.move(scaled_dx, scaled_dy)
    return f"successfully moved mouse by ({dx}, {dy}) pixels"

def look_right():
    move_mouse_relative_to_current_position(1500, 0)
    move_mouse_relative_to_current_position(500, 0)
    return "camera right"
def look_left():
    move_mouse_relative_to_current_position(-1500, 0)
    move_mouse_relative_to_current_position(-500, 0)
    return "camera left"
def look_down():
    move_mouse_relative_to_current_position(0, 1500)
    move_mouse_relative_to_current_position(0, 500)
    return "camera down"
def look_up():
    move_mouse_relative_to_current_position(0, -1500)
    move_mouse_relative_to_current_position(0, -500)
    return "camera up"
import time
async def hold_key_for_duration(key: str, duration: float) -> str:
    """Hold a keyboard key for a specified duration.
    
    Args:
        key: The key to hold (e.g., 'w', 'a', 's', 'd', 'space')
        duration: How long to hold the key in seconds
    """
    pydirectinput.keyDown(key)
            # Check periodically so we are responsive to cancellation
    time.sleep(duration)
    pydirectinput.keyUp(key)    
    return f"started holding '{key}' for {duration} seconds (checking video feed...)"
async def run():
    await asyncio.sleep(2)
    await hold_key_for_duration("d", 1)
    # await asyncio.sleep(2)
    # await hold_key_for_duration("d", 2)
    return

if __name__ == "__main__":
    asyncio.run(run())