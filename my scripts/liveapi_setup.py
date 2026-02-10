

import asyncio
from google import genai
from google.genai import types
import os
import asyncio
from dotenv import load_dotenv
import io
import mss
import PIL.Image
import pyaudio
import time
import threading
import pyautogui
import pydirectinput

import vertexai
from vertexai.generative_models import GenerativeModel

from pynput import keyboard, mouse



load_dotenv()


# Global variable to track message send timestamp
last_message_sent_time = None

# Global flag to save next frame on demand
save_next_frame = False

# Global sync: track when screenshot is sent and current action
screen_sent_event = None  # Will be set to asyncio.Event() in run()

# Global active actions queue - tracks what inputs are currently happening
# Each entry: {"description": "...", "end_time": float or None}
import threading
active_actions_lock = threading.Lock()
active_actions = []

MODEL_NAME = 'gemini-2.0-flash-live-preview-04-09'

SYSTEM_INSTRUCTION = """
You are an autonomous game-playing AI agent in Terraria. You control a character using keyboard and mouse tools. 
Your goal is to accomplish your given tasks using provided tools.

### CRITICAL: HOW YOU PERCEIVE THE WORLD
**Visuals:** You receive a video stream (1 FPS). 

### CAPABILITIES & TOOLS
- AD: Move (A=left, D=right) using "hold_key_for_duration" tool
- Space: Jump using "press_key" tool and press the spacebar
- Attack: left click
- Break stuff: hold left click 
- Aim: mouse tools

### Tasks:
- find a chest and stand next to it

### Rules:
- Always call 1 tool at a time, describe what you see in detail to see if you accomplished the goal you set out to do with your previous tool call before moving on, then repeat.
"""

CONFIG = {"response_modalities": ["TEXT"], 
        "realtime_input_config": {
            "automatic_activity_detection": {
                "disabled": True  
            }
        },
        "system_instruction": SYSTEM_INSTRUCTION
        # "output_audio_transcription": {},
        
    }

async def send_screen(session):
    """Captures the screen and sends 1 frame per second to Gemini."""
    sct = mss.mss()
    monitor = sct.monitors[1]  # Primary monitor (0 = all monitors combined)
    saved_debug = False  # Debug flag to save first frame
    
    
    while True:
        # Capture the screen
        screenshot = sct.grab(monitor)
        
        # Convert to PIL Image
        img = PIL.Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
        
        # Get cursor position and offset relative to this monitor
        abs_x, abs_y = pyautogui.position()
        cursor_x = abs_x - monitor["left"]
        cursor_y = abs_y - monitor["top"]
        
        # Draw a visible cursor marker (only if cursor is on this monitor)
        from PIL import ImageDraw
        
        size = 2  # Size on resized image
        
        # Resize first
        new_width, new_height = 768, 432
        img = img.resize((new_width, new_height), PIL.Image.BILINEAR)
        
        # Scale cursor position to match resized image
        scale_x = new_width / monitor["width"]
        scale_y = new_height / monitor["height"]
        # scaled_cursor_x = int(cursor_x * scale_x)
        # scaled_cursor_y = int(cursor_y * scale_y)
        
        # # Create draw object on resized image
        # draw = ImageDraw.Draw(img)
        
        # if 0 <= cursor_x <= monitor["width"] and 0 <= cursor_y <= monitor["height"]:
        #     # Filled red circle with white border for visibility
        #     draw.ellipse([scaled_cursor_x - size, scaled_cursor_y - size, 
        #                   scaled_cursor_x + size, scaled_cursor_y + size], 
        #                  fill='red')
        # Save frame on demand (triggered by 'save' command)
        global save_next_frame
        if save_next_frame:
            timestamp = int(time.time())
            filename = f"frame_{timestamp}.png"
            img.save(filename)
            print(f"[SAVED] {filename}")
            save_next_frame = False
        # Convert to JPEG bytes
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        jpeg_bytes = buffer.getvalue()
        
        # Send to Gemini as a Blob
        await session.send_realtime_input(
            video=types.Blob(data=jpeg_bytes, mime_type='image/jpeg')
        )
        
        # Send active actions as context with each frame
        with active_actions_lock:
            # Clean up expired actions
            current_time = time.time()
            active_actions[:] = [a for a in active_actions if a.get('end_time') is None or current_time < a['end_time']]
            
            if active_actions:
                descriptions = [a['description'] for a in active_actions]
                await add_context(session, f"[Active inputs: {'; '.join(descriptions)}]")
        
        # Signal that screen was sent (for tool response sync)
        global screen_sent_event
        if screen_sent_event is not None:
            screen_sent_event.set()
        
        # Wait 1 second before next frame
        await asyncio.sleep(1)

async def listen_audio(session):
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    SEND_SAMPLE_RATE = 16000
    CHUNK_SIZE = 1024

    pya = pyaudio.PyAudio()
    audio_stream = await asyncio.to_thread(
        pya.open,
        format=FORMAT,
        channels=CHANNELS,
        rate=SEND_SAMPLE_RATE,
        input=True,
        input_device_index=29,
        frames_per_buffer=CHUNK_SIZE,
    )

    try:
        while True:
            data = await asyncio.to_thread(audio_stream.read, CHUNK_SIZE, exception_on_overflow=False)  
            await session.send_realtime_input(
                audio=types.Blob(data=data, mime_type='audio/pcm')
            )
    except asyncio.CancelledError:
        audio_stream.stop_stream()
        audio_stream.close()
        pya.terminate()
        print("\n[Audio capture stopped]")
        return          
ALL_KEYS = [
    'a','b','c','d','e','f','g','h','i','j','k','l','m',
    'n','o','p','q','r','s','t','u','v','w','x','y','z',
    '0','1','2','3','4','5','6','7','8','9',
    'shift','ctrl','alt','tab','space','enter',
    'up','down','left','right'
]
def stop_keyboard_inputs():
    """Release all keyboard keys. Use this to stop all movement or input."""
    for key in ALL_KEYS:
        pydirectinput.keyUp(key)
        pydirectinput.mouseUp()

async def handle_response(session):
    global last_message_sent_time

    while True:
        try:
            async for response in session.receive():
                # 1. Handle text response
                if response.server_content and response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if part.text:
                            # Measure response delay
                            if last_message_sent_time is not None:
                                delay_ms = (time.time() - last_message_sent_time) * 1000
                                print(f"\n[Response delay: {delay_ms:.2f}ms]")
                                last_message_sent_time = None 
                            print(part.text, end="", flush=True)

                # 2. Handle Tool Calls
                if response.tool_call:
                    print(f"\n[Tool Call Detected]")
                    function_responses = []
                    # stop_keyboard_inputs()
                    # Iterate through all function calls in this turn
                    print("Tool calls: ", response.tool_call)
                    
                    # Add actions to the queue BEFORE executing
                    action_entries = []
                    for fc in response.tool_call.function_calls:
                        args_str = ", ".join(f"{k}={v}" for k, v in fc.args.items()) if fc.args else ""
                        description = f"{fc.name}({args_str})"
                        
                        # Estimate end time if duration is provided
                        end_time = None
                        if 'duration' in fc.args:
                            end_time = time.time() + float(fc.args['duration'])
                        
                        action_entry = {"description": description, "end_time": end_time, "id": fc.id}
                        action_entries.append(action_entry)
                        
                        with active_actions_lock:
                            active_actions.append(action_entry)
                    
                    print(f"[Added {len(action_entries)} actions to queue]")
                    
                    # NOW execute the tools
                    for fc in response.tool_call.function_calls:
                        func_name = fc.name
                        func_args = fc.args
                        call_id = fc.id
                        
                        # Execute the function if it exists in our map
                        if func_name in tools_map:
                            try:
                                result = tools_map[func_name](**func_args)
                                if asyncio.iscoroutine(result):
                                    result = await result
                                response_content = {'result': result}
                            except Exception as e:
                                response_content = {'error': str(e)}
                        else:
                            response_content = {'error': 'Function not found'}
                        
                        # Remove this action from the queue after execution
                        with active_actions_lock:
                            active_actions[:] = [a for a in active_actions if a.get('id') != call_id]

                        # Create the response object
                        function_responses.append(types.FunctionResponse(
                            name=func_name,
                            id=call_id,
                            response={
    'result': 'CHECK IMAGE FEED AND DESCRIBE IT IN DETAIL, AFTERWARDS READ WHAT YOU JUST DESCRIBED TO MAKE YOUR NEXT DECISION!'
  }
                        ))

                    # Send the results back to the model

                    # Wait for next screen update before sending tool response
                    global screen_sent_event
                    if screen_sent_event is not None:
                        screen_sent_event.clear()  # Reset the event
                        print("[Waiting for screen update...]")
                        await screen_sent_event.wait()  # Wait until screen is sent
                    
                    # Get current active actions to include in response
                    with active_actions_lock:
                        current_active = [a['description'] for a in active_actions]
                    
                    # Modify function responses to include what's currently active
                    if current_active:
                        for fr in function_responses:
                            fr.response['active_inputs'] = current_active # THIS DOESNT EVEN WORK IT DOESNT ADD IT TO THE RESPONSE
                            fr.response['instructions for gemini'] = "CHECK IMAGE FEED AND DESCRIBE IT IN DETAIL, AFTERWARDS READ WHAT YOU JUST DESCRIBED TO MAKE YOUR NEXT DECISION!"
                    print(function_responses)

                    print(f"Sending results back... (Active inputs: {current_active})")
                    await session.send_tool_response(
                        function_responses=function_responses
                    )

                    

        except Exception as e:
            print(f"Error in handle_response: {e}")
            break
                


async def add_context(session, context_text):
    await session.send_client_content(
        turns=types.Content(
            role="user",
            parts=[types.Part(text=context_text)]
        ),
        turn_complete=False  
    )

async def nudge_llm(session):
    """Send an empty message to nudge the LLM to continue taking actions."""
    while True:
        await session.send_realtime_input(text="What do you see? Decide what tool to call to achieve your tasks based on this.")
        await asyncio.sleep(5)

async def send_text(session):
    while True:
        # Runs input() in a separate thread so it doesn't freeze the app
        text = await asyncio.to_thread(input, "message > ")
        
        if text.lower() == "q": break
        # Save current frame
        elif text.lower() == "save":
            global save_next_frame
            save_next_frame = True
            print("[INFO] Will save next frame...")
        # check if adding context
        elif text.startswith("ADDCONTEXT "):
            remainder = text[len("ADDCONTEXT "):]
            await add_context(session, remainder)
        else:
            # Record timestamp before sending
            global last_message_sent_time
            last_message_sent_time = time.time()
            
            # Sends the text to the session
            # await session.send_realtime_input(activity_start = {})
            await session.send_realtime_input(text=text)
            # await session.send_realtime_input(activity_end = {})

def get_last_name(first_name: str) -> str:
    """Get the last name for a given first name. (Example tool for LiveAPI testing)
    
    Args:
        first_name: The first name to look up
    """
    return "unknown"


tools_map = {}


# Global variable to hold the current async movement task
current_movement_task = None

# All possible keys for safety release
ALL_KEYS = ['w', 'a', 's', 'd', 'space', 'shift', 'ctrl', 'e', 'q', 'r', 'f', 'c', 'x', 'z', 'tab', 'escape']

async def hold_key_for_duration(key: str, duration: float) -> str:
    """Hold a keyboard key for a specified duration.
    
    Args:
        key: The key to hold (e.g., 'w', 'a', 's', 'd', 'space')
        duration: How long to hold the key in seconds
    """
    global current_movement_task

    # 1. CANCEL any existing movement task before starting a new one
    if current_movement_task and not current_movement_task.done():
        print(f"[System] Cancelling previous movement to start new one...")
        current_movement_task.cancel()
        # Brief yield to let the cancellation process
        await asyncio.sleep(0.01)

    # 2. Define the worker that handles the key press
    async def _hold():
        try:
            pydirectinput.keyDown(key)
            # Check periodically so we are responsive to cancellation
            end_time = time.time() + duration
            while time.time() < end_time:
                await asyncio.sleep(0.1)
            pydirectinput.keyUp(key)
        except asyncio.CancelledError:
            # IMPORTANT: Ensure key is released if task is cancelled
            pydirectinput.keyUp(key)
            print(f"[System] Movement '{key}' was cancelled cleanly.")
            raise  # Re-raise to satisfy asyncio

    # 3. Create the task and store it globally
    current_movement_task = asyncio.create_task(_hold())
    
    return f"CHECK IMAGE FEED AND DESCRIBE IT IN DETAIL, AFTERWARDS READ WHAT YOU JUST DESCRIBED TO MAKE YOUR NEXT DECISION!"

def stop_keyboard_inputs() -> str:
    """Release all keyboard keys and CANCEL ongoing movement tasks."""
    global current_movement_task
    
    # 1. Cancel the specific async task
    if current_movement_task and not current_movement_task.done():
        current_movement_task.cancel()
    
    # 2. Physical safety release
    for key in ALL_KEYS:
        pydirectinput.keyUp(key)
    pydirectinput.mouseUp()
    
    # 3. Clear the context list immediately so the next prompt knows we stopped
    with active_actions_lock:
        active_actions.clear()

    return "STOPPED all movement and cancelled active tasks."

def press_key(key: str) -> str:
    """Press and release a keyboard key once.
    
    Args:
        key: The key to press (e.g., 'e', 'space', 'enter', 'p')
    """
    pydirectinput.press(key)
    return f"successfully pressed '{key}'"
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
    
    pydirectinput.move(scaled_dx, scaled_dy)
    return f"successfully moved mouse by ({dx}, {dy}) pixels"

def move_mouse_to_position(x: int, y: int) -> str:
    """Move the mouse cursor to an absolute screen position.
    
    Args:
        x: The x coordinate (0 = left edge, 767 = right edge)
        y: The y coordinate (0 = top edge, 431 = bottom edge)
    """
    real_x = int(x * X_SCALE)
    real_y = int(y * Y_SCALE)
    
    # Clamp to screen bounds just in case
    real_x = max(0, min(real_x, REAL_WIDTH - 1))
    real_y = max(0, min(real_y, REAL_HEIGHT - 1))

    pydirectinput.moveTo(real_x, real_y)
    return f"moved mouse to ({x}, {y})"

def left_click() -> str:
    """Perform a left mouse click at the current cursor position."""
    pydirectinput.click()
    return "successfully performed left click"

def hold_left_click(duration: float) -> str:
    """Hold the left mouse button for a specified duration.
    
    Args:
        duration: How long to hold the left mouse button in seconds
    """
    pydirectinput.mouseDown()
    time.sleep(duration)
    pydirectinput.mouseUp()
    return f"held left click for {duration} seconds"



tools_map.update(
    {
        "stop_keyboard_inputs": stop_keyboard_inputs,
        "hold_key_for_duration": hold_key_for_duration,
        "press_key": press_key,
        "move_mouse_relative_to_current_position": move_mouse_relative_to_current_position,
        "move_mouse_to_position": move_mouse_to_position,
        "left_click": left_click,
        "hold_left_click": hold_left_click,

    }
)

CONFIG["tools"] = list(tools_map.values())


async def run():
    #
    await asyncio.sleep(1)
    print(hold_left_click(0.1))
    print(hold_left_click(0.1))
    return
    #
    client = genai.Client(http_options=types.HttpOptions(api_version="v1beta1"))
    async with client.aio.live.connect(
        model=MODEL_NAME,
        config=CONFIG
    ) as session:
        # Initialize the screen sync event
        global screen_sent_event
        screen_sent_event = asyncio.Event()
        
        # bg tasks
        response_task = asyncio.create_task(handle_response(session))
        screen_task = asyncio.create_task(send_screen(session))

        # await send_text(session)
        await nudge_llm(session)
        
        response_task.cancel()
        screen_task.cancel()


        
        
        
        

    
        

if __name__ == "__main__":
    asyncio.run(run())