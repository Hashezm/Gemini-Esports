# Visual LLM Reaction Time Test - LLM sees events on screen

import asyncio
import random
import time
import io
import mss
import PIL.Image
import tkinter as tk
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Global tkinter root and label
root = None
label = None

# Latency and accuracy tracking
event_shown_time = None
current_expected_action = None  # What the LLM should call
results = []

def setup_display():
    """Create a simple fullscreen-ish window to show events."""
    global root, label
    root = tk.Tk()
    root.title("Reaction Test")
    root.geometry("800x400")
    root.configure(bg='black')
    
    label = tk.Label(root, text="READY", font=('Arial', 72, 'bold'), 
                     fg='white', bg='black')
    label.pack(expand=True)
    
    root.update()

def show_event(event_text):
    """Update the display with the current event."""
    global label, root
    
    # Color based on event
    if "left" in event_text:
        color = 'red'
    elif "right" in event_text:
        color = 'orange'
    else:
        color = 'green'
    
    label.config(text=event_text.upper(), fg=color)
    root.update()

async def send_screen(session):
    """Captures the screen and sends 1 frame per second to Gemini."""
    sct = mss.mss()
    monitor = sct.monitors[1]
    
    while True:
        screenshot = sct.grab(monitor)
        img = PIL.Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
        img.thumbnail((768, 768))
        
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=80)
        jpeg_bytes = buffer.getvalue()
        
        await session.send_realtime_input(
            video=types.Blob(data=jpeg_bytes, mime_type='image/jpeg')
        )
        await asyncio.sleep(1)

MODEL_NAME = 'gemini-2.0-flash-live-preview-04-09'

# Simple game functions
def move_left() -> str:
    """Move the car left to avoid an obstacle on the right."""
    return "moved_left"

def move_right() -> str:
    """Move the car right to avoid an obstacle on the left."""
    return "moved_right"

tools_map = {
    "move_left": move_left,
    "move_right": move_right,
}

CONFIG = {
    "response_modalities": ["TEXT"],
    "realtime_input_config": {
        "automatic_activity_detection": {"disabled": True}
    },
    "system_instruction": """You are controlling a car in a reaction game. Watch the screen for events.
When you SEE "OBSTACLE LEFT" on screen, call move_right immediately.
When you SEE "OBSTACLE RIGHT" on screen, call move_left immediately.
When you SEE "ROAD CLEAR" on screen, do nothing.
React as fast as possible based on what you see!""",
    "tools": list(tools_map.values())
}

async def handle_response(session):
    global event_shown_time, results
    
    while True:
        try:
            async for response in session.receive():
                # Debug: print what we're receiving
                if response.server_content and response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if part.text:
                            print(f"  [LLM text]: {part.text}")
                
                if response.tool_call:
                    # Calculate latency
                    latency_ms = (time.time() - event_shown_time) * 1000 if event_shown_time else 0
                    
                    function_responses = []
                    for fc in response.tool_call.function_calls:
                        is_correct = (fc.name == current_expected_action)
                        status = "✓" if is_correct else "✗"
                        print(f"  → LLM called: {fc.name} {status} (latency: {latency_ms:.0f}ms)")
                        results.append({"action": fc.name, "expected": current_expected_action, "correct": is_correct, "latency_ms": latency_ms})
                        
                        result = tools_map[fc.name](**fc.args) if fc.name in tools_map else "error"
                        function_responses.append(types.FunctionResponse(
                            name=fc.name,
                            id=fc.id,
                            response={"result": result}
                        ))
                    
                    await session.send_tool_response(function_responses=function_responses)
                    
        except Exception as e:
            print(f"Error: {e}")
            break

async def run_test(num_events=10, interval=2.0):
    global event_shown_time, current_expected_action, results
    results = []
    events = ["obstacle left", "obstacle right", "road clear"]
    
    # Map events to expected actions
    expected_actions = {
        "obstacle left": "move_right",
        "obstacle right": "move_left",
        "road clear": None  # No action expected
    }
    
    setup_display()
    
    client = genai.Client(http_options=types.HttpOptions(api_version="v1beta1"))
    
    async with client.aio.live.connect(model=MODEL_NAME, config=CONFIG) as session:
        response_task = asyncio.create_task(handle_response(session))
        screen_task = asyncio.create_task(send_screen(session))
        
        print(f"\n=== Visual Reaction Test ({num_events} events) ===")
        print("(LLM is watching your screen)\n")
        
        # Give it a moment to start seeing the screen
        await asyncio.sleep(2)
        await session.send_realtime_input(text="we will start the game now.")
        await asyncio.sleep(2)
        for i in range(num_events):
            event = random.choice(events)
            current_expected_action = expected_actions[event]
            print(f"[{i+1}/{num_events}] Showing: {event}")
            event_shown_time = time.time()
            show_event(event)
            await asyncio.sleep(0.3)
            # Prompt the LLM to look at the screen and react
            await session.send_realtime_input(text="Look at my screen and react now!")
            
            await asyncio.sleep(interval)
        
        show_event("DONE")
        await asyncio.sleep(2)
        
        response_task.cancel()
        screen_task.cancel()
        
        # Print results
        print("\n=== Results ===")
        if results:
            avg_latency = sum(r["latency_ms"] for r in results) / len(results)
            correct = sum(1 for r in results if r["correct"])
            accuracy = (correct / len(results)) * 100
            
            print(f"Total responses: {len(results)}")
            print(f"Accuracy: {correct}/{len(results)} ({accuracy:.0f}%)")
            print(f"Average latency: {avg_latency:.0f}ms")
            print(f"Min: {min(r['latency_ms'] for r in results):.0f}ms")
            print(f"Max: {max(r['latency_ms'] for r in results):.0f}ms")
        else:
            print("No tool calls received")
        
        root.destroy()

if __name__ == "__main__":
    asyncio.run(run_test(num_events=10, interval=2.0))
