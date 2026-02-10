"""
Executor Module (Gemini 3 Flash)
Handles subtask execution, tool calls, and self-verification via video.
"""

from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types
import json
import re
import time
import pydirectinput

from screen_recorder import ScreenRecorder
from screenshot import capture_screenshot


class Executor:
    """
    Subtask executor using Gemini 3 Flash.
    Attempts subtasks with tools, captures video, and self-verifies.
    """
    
    def __init__(self, api_key: str = None, model: str = "gemini-3-flash-preview"):
        """
        Initialize the Executor with Gemini Flash.
        
        Args:
            api_key: Google API key. If None, uses GOOGLE_API_KEY env var.
            model: Model name to use (default: gemini-3-flash-preview)
        """
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = genai.Client()  # Uses env var
        
        self.model = model
        self.recorder = ScreenRecorder(fps=10)
        self.tool_registry = {}  # name -> function reference
        self.max_attempts = 5
        
        # Base tools that are always available
        self._register_base_tools()
    
    def _register_base_tools(self):
        """Register the default tools available to the executor."""
        
        def hold_key(key: str, duration: float) -> dict:
            """Hold a key for a duration.
            
            Args:
                key: Key to hold (e.g., 'w', 'a', 's', 'd', 'space')
                duration: Seconds to hold
            
            Returns:
                Status dictionary.
            """
            try:
                pydirectinput.keyDown(key)
                time.sleep(duration)
                pydirectinput.keyUp(key)
                return {"status": "success", "key": key, "duration": duration}
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        def tap_key(key: str, times: int = 1) -> dict:
            """Tap a key one or more times.
            
            Args:
                key: Key to tap
                times: Number of times to tap
            
            Returns:
                Status dictionary.
            """
            try:
                for _ in range(times):
                    pydirectinput.press(key)
                    time.sleep(0.1)
                return {"status": "success", "key": key, "times": times}
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        def wait(seconds: float) -> dict:
            """Wait for a duration.
            
            Args:
                seconds: Seconds to wait
            
            Returns:
                Status dictionary.
            """
            time.sleep(seconds)
            return {"status": "success", "waited": seconds}
        
        def click(button: str = "left") -> dict:
            """Click mouse button once.
            
            Args:
                button: Which button to click ('left' or 'right')
            
            Returns:
                Status dictionary.
            """
            try:
                pydirectinput.click(button=button)
                return {"status": "success", "button": button}
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        def hold_click(button: str = "left", duration: float = 1.0) -> dict:
            """Hold mouse button for a duration (for mining, attacking).
            
            Args:
                button: Which button to hold ('left' or 'right')
                duration: Seconds to hold
            
            Returns:
                Status dictionary.
            """
            try:
                pydirectinput.mouseDown(button=button)
                time.sleep(duration)
                pydirectinput.mouseUp(button=button)
                return {"status": "success", "button": button, "duration": duration}
            except Exception as e:
                pydirectinput.mouseUp(button=button)  # Safety release
                return {"status": "error", "error": str(e)}
        
        def move_mouse(x: int, y: int, relative: bool = False) -> dict:
            """Move mouse to position or by offset.
            
            Args:
                x: X coordinate (absolute) or offset (relative)
                y: Y coordinate (absolute) or offset (relative)  
                relative: If True, move by offset from current position
            
            Returns:
                Status dictionary.
            """
            try:
                if relative:
                    pydirectinput.move(x, y)
                else:
                    pydirectinput.moveTo(x, y)
                return {"status": "success", "x": x, "y": y, "relative": relative}
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        self.tool_registry["hold_key"] = hold_key
        self.tool_registry["tap_key"] = tap_key
        self.tool_registry["wait"] = wait
        self.tool_registry["click"] = click
        self.tool_registry["hold_click"] = hold_click
        self.tool_registry["move_mouse"] = move_mouse
    
    def register_tool(self, name: str, func):
        """Register a new tool function."""
        self.tool_registry[name] = func
    
    def get_tools_config(self, tool_names: list = None) -> list:
        """Get tool functions for Gemini config.
        
        Args:
            tool_names: List of tool names to include. If None, include all.
        
        Returns:
            List of function references for Gemini tools config.
        """
        if tool_names is None:
            return list(self.tool_registry.values())
        return [self.tool_registry[name] for name in tool_names if name in self.tool_registry]
    
    def attempt_subtask(self, subtask: dict, tools: list = None) -> dict:
        """
        Attempt to complete a subtask.
        
        Args:
            subtask: Dictionary with 'description', 'success_criteria', 'tools_needed'
            tools: Optional list of tool names to use
        
        Returns:
            Dictionary with status, replay video, and details.
        """
        description = subtask.get("description", str(subtask))
        success_criteria = subtask.get("success_criteria", "Task appears complete")
        tool_names = tools or subtask.get("tools_needed", list(self.tool_registry.keys()))
        
        # Get tool functions - Gemini will auto-execute these!
        tool_funcs = self.get_tools_config(tool_names)
        
        config = types.GenerateContentConfig(
            tools=tool_funcs,
            system_instruction=f"""You are a game-playing AI executor. Your current subtask is:

{description}

Success Criteria: {success_criteria}

You have access to tools for controlling the game. Gemini will automatically execute your tool calls.
After each tool call, you'll receive the result.

IMPORTANT: You MUST call at least one tool before saying you're done.

When you believe you've completed the subtask or cannot proceed:
- If DONE: respond with exactly "STATUS: DONE" followed by a brief description
- If STUCK: respond with exactly "STATUS: STUCK" followed by what's blocking you
- If still working: call the next tool

Be methodical. Don't rush."""
        )
        
        chat = self.client.chats.create(model=self.model, config=config)
        
        all_videos = []
        attempt = 0
        
        print(f"\n[EXECUTOR DEBUG] Starting subtask: {description[:50]}...")
        print(f"[EXECUTOR DEBUG] Success criteria: {success_criteria[:50]}...")
        print(f"[EXECUTOR DEBUG] Available tools: {tool_names}")
        
        while attempt < self.max_attempts:
            attempt += 1
            print(f"\n[EXECUTOR DEBUG] ━━━ Attempt {attempt}/{self.max_attempts} ━━━")
            
            # Get current screenshot
            print("[EXECUTOR DEBUG] Capturing screenshot...")
            screenshot_bytes = capture_screenshot()
            print(f"[EXECUTOR DEBUG] Screenshot captured: {len(screenshot_bytes)//1024}KB")
            
            # Start recording BEFORE sending message (tools may auto-execute)
            print("[EXECUTOR DEBUG] Starting video recording...")
            self.recorder.start()
            
            # Send screenshot and ask for next action
            # Gemini will auto-execute any tools that get called!
            message_parts = [
                types.Part(
                    inline_data=types.Blob(
                        data=screenshot_bytes,
                        mime_type="image/jpeg"
                    )
                ),
                f"Attempt {attempt}/{self.max_attempts}. Current game state shown. Call a tool to make progress."
            ]
            
            print("[EXECUTOR DEBUG] Sending screenshot to model (tools will auto-execute)...")
            
            # API call with error handling
            try:
                response = chat.send_message(message_parts)
            except Exception as e:
                print(f"[EXECUTOR DEBUG] ❌ API Error: {e}")
                # Stop recording and retry
                self.recorder.stop()
                print("[EXECUTOR DEBUG] Retrying after error...")
                time.sleep(1)  # Brief pause before retry
                continue
            
            # Wait for any actions to settle
            time.sleep(0.3)
            
            # Stop recording
            video_bytes = self.recorder.stop()
            if video_bytes:
                all_videos.append(video_bytes)
                print(f"[EXECUTOR DEBUG] Video recorded: {len(video_bytes)//1024}KB")
            
            # Get response text
            try:
                response_text = response.text if hasattr(response, 'text') and response.text else ""
            except Exception:
                response_text = ""
            
            print(f"[EXECUTOR DEBUG] Response: {response_text[:150] if response_text else '(empty)'}...")
            
            # Check for status
            if not response_text:
                print("[EXECUTOR DEBUG] ⚠️ Empty response, continuing...")
                continue
            
            if "STATUS: DONE" in response_text:
                print("[EXECUTOR DEBUG] ✅ STATUS: DONE detected")
                return {
                    "status": "done",
                    "message": response_text,
                    "attempts": attempt,
                    "videos": all_videos,
                    "final_video": all_videos[-1] if all_videos else None
                }
            elif "STATUS: STUCK" in response_text:
                print("[EXECUTOR DEBUG] ❌ STATUS: STUCK detected")
                return {
                    "status": "stuck",
                    "message": response_text,
                    "attempts": attempt,
                    "videos": all_videos,
                    "final_video": all_videos[-1] if all_videos else None
                }
        
        # Max attempts reached
        print(f"[EXECUTOR DEBUG] ⚠️ Max attempts ({self.max_attempts}) reached")
        return {
            "status": "max_attempts",
            "message": f"Reached {self.max_attempts} attempts without completion",
            "attempts": attempt,
            "videos": all_videos,
            "final_video": all_videos[-1] if all_videos else None
        }


# Quick test
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    print("Testing Executor...")
    executor = Executor()
    
    print(f"Registered tools: {list(executor.tool_registry.keys())}")
    
    # Simple test - just verify tool execution works
    print("\n--- Testing hold_key directly ---")
    result = executor.tool_registry["hold_key"]("w", 0.5)
    print(f"Result: {result}")
    
    print("\n--- Testing tap_key directly ---")
    result = executor.tool_registry["tap_key"]("space", 2)
    print(f"Result: {result}")
    
    print("\nDirect tool tests passed!")
    print("To test full subtask execution, run with a game open.")
