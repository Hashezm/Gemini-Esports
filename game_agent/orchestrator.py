"""
Orchestrator Module (Gemini 3 Pro)
Handles high-level planning, task decomposition, and failure diagnosis.
"""

from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types
import json
import re


class Orchestrator:
    """
    High-level planner using Gemini 3 Pro.
    Breaks goals into subtasks, requests tools, and diagnoses failures.
    """
    
    def __init__(self, api_key: str = None, model: str = "gemini-3-pro-preview"):
        """
        Initialize the Orchestrator with Gemini Pro.
        
        Args:
            api_key: Google API key. If None, uses GOOGLE_API_KEY env var.
            model: Model name to use (default: gemini-3-pro-preview)
        """
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = genai.Client()  # Uses env var
        
        self.model = model
        
        # System instruction for planning
        self.planning_config = {
            "system_instruction": """You are a game-playing AI orchestrator. Your job is to:
1. Break down high-level goals into concrete subtasks
2. Determine what tools/actions are needed for each subtask
3. Provide clear success criteria for each subtask

IMPORTANT: Create a COMPLETE plan that GUARANTEES the goal will be achieved.
- Include AT LEAST 3-5 subtasks for any non-trivial goal
- Include ITERATION steps (e.g., "Repeat walking right until a cave is found")
- Include FALLBACK steps (e.g., "If no cave found, try digging down")

CONSTRAINTS:
- You can ONLY control keyboard and mouse input (press keys, hold keys, click)
- You can see the screen via screenshots, but CANNOT read game memory
- All perception comes from VISUAL analysis of screenshots

AVAILABLE BASE TOOLS:
- hold_key(key, duration): Hold a key for seconds (for movement)
- tap_key(key, times): Tap a key N times (for jumping, attacking)
- wait(seconds): Pause execution
- click(button): Click left or right mouse button
- hold_click(button, duration): Hold mouse button for mining/attacking
- move_mouse(x, y, relative): Move mouse to position or by offset

When given a goal, respond with a JSON object in this exact format:
{
    "subtasks": [
        {
            "id": 1,
            "description": "Clear, specific action to take",
            "tools_needed": ["hold_key", "tap_key"],
            "success_criteria": "Visual indicator that can be seen in screenshot",
            "estimated_duration": "rough time estimate"
        }
    ]
}

PLANNING RULES:
1. Create enough subtasks to FULLY complete the goal, not just start it
2. Each subtask should have CLEAR visual success criteria
3. Include verification steps (e.g., "Confirm cave entrance is visible")
4. If a goal requires searching, include MULTIPLE search attempts in different directions
5. The final subtask should directly achieve the stated goal"""
        }
        
        self.chat = None
    
    def plan(self, goal: str, game_context: str = None, screenshot: bytes = None) -> dict:
        """
        Break a high-level goal into subtasks.
        
        Args:
            goal: The high-level objective (e.g., "Find iron ore in Terraria")
            game_context: Optional context about the game/current state
            screenshot: Optional screenshot bytes showing current game state
        
        Returns:
            Dictionary with subtasks and their requirements.
        """
        self.chat = self.client.chats.create(
            model=self.model,
            config=self.planning_config
        )
        
        # Build the message parts
        message_parts = []
        
        # Add screenshot if provided
        if screenshot:
            message_parts.append(
                types.Part(
                    inline_data=types.Blob(
                        data=screenshot,
                        mime_type="image/jpeg"
                    )
                )
            )
        
        # Build text prompt
        prompt = f"Goal: {goal}"
        if game_context:
            prompt += f"\n\nGame Context:\n{game_context}"
        if screenshot:
            prompt += "\n\nI've attached a screenshot of the current game state. Use this to inform your plan."
        
        message_parts.append(prompt)
        
        response = self.chat.send_message(message_parts)
        
        # Parse JSON from response
        try:
            # Try to extract JSON from the response
            text = response.text
            # Find JSON in the response (might be wrapped in markdown)
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                return json.loads(json_match.group())
            else:
                return {"error": "Could not parse plan", "raw": text}
        except json.JSONDecodeError:
            return {"error": "Invalid JSON in response", "raw": response.text}
    
    def request_tool(self, tool_description: str) -> str:
        """
        Request a new tool to be created by the code agent.
        
        Args:
            tool_description: What the tool should do
        
        Returns:
            Python code for the tool function.
        """
        code_config = {
            "system_instruction": """You write Python functions for game automation.
Follow this exact format:

def function_name(param1: type1, param2: type2 = default) -> dict[str, any]:
    \"\"\"Brief description.
    
    Args:
        param1: Description
        param2: Description (default: value)
    
    Returns:
        A dictionary with status and result.
    \"\"\"
    try:
        # Implementation
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}

Rules:
- Use pydirectinput for keyboard/mouse (already imported)
- Use time.sleep() for delays (already imported)
- Return dict with "status" key
- Include try-except
- NO imports in your code"""
        }
        
        chat = self.client.chats.create(model=self.model, config=code_config)
        response = chat.send_message(f"Create a tool that: {tool_description}")
        
        # Extract code (remove markdown if present)
        code = response.text
        code = re.sub(r'^```python\s*', '', code)
        code = re.sub(r'\s*```$', '', code)
        
        return code.strip()
    
    def diagnose_failure(self, subtask: dict, video_bytes: bytes, error_info: str = None) -> dict:
        """
        Analyze a failed subtask attempt using video replay.
        
        Args:
            subtask: The subtask that failed
            video_bytes: Video recording of the failed attempt
            error_info: Any error messages or status from the executor
        
        Returns:
            Dictionary with diagnosis and suggested fixes.
        """
        diagnosis_config = {
            "system_instruction": """You are analyzing why a game task failed.
Watch the video carefully and determine:
1. What went wrong
2. Why it went wrong  
3. How to fix it

Respond with JSON:
{
    "diagnosis": "What happened",
    "root_cause": "Why it failed",
    "suggested_fix": "How to solve it",
    "needs_new_tool": true/false,
    "new_tool_description": "Description if new tool needed, else null",
    "retry_with_modifications": "Modified instructions if should retry, else null"
}"""
        }
        
        chat = self.client.chats.create(model=self.model, config=diagnosis_config)
        
        message_parts = [
            types.Part(
                inline_data=types.Blob(
                    data=video_bytes,
                    mime_type="video/mp4"
                ),
                video_metadata=types.VideoMetadata(fps=10)
            ),
            f"""The executor tried to complete this subtask but reported failure:

Subtask: {subtask.get('description', subtask)}
Success Criteria: {subtask.get('success_criteria', 'Not specified')}
Error Info: {error_info or 'No specific error'}

Watch the video and diagnose what went wrong."""
        ]
        
        response = chat.send_message(message_parts)
        
        try:
            json_match = re.search(r'\{[\s\S]*\}', response.text)
            if json_match:
                return json.loads(json_match.group())
            return {"diagnosis": response.text, "needs_new_tool": False}
        except json.JSONDecodeError:
            return {"diagnosis": response.text, "needs_new_tool": False}
    
    def google_search(self, query: str) -> str:
        """
        Search for game information using Gemini's built-in search.
        
        Args:
            query: What to search for
        
        Returns:
            Relevant information as text.
        """
        search_config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
        
        response = self.client.models.generate_content(
            model=self.model,
            contents=f"Search for and summarize: {query}",
            config=search_config
        )
        
        return response.text


# Quick test
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    print("Testing Orchestrator...")
    orchestrator = Orchestrator()
    
    # Test planning
    print("\n--- Testing plan() ---")
    plan = orchestrator.plan(
        goal="In Terraria, walk to the right until we find a cave entrance",
        game_context="Player is standing on surface, daytime, forest biome"
    )
    print(json.dumps(plan, indent=2))
    
    # Test tool request
    print("\n--- Testing request_tool() ---")
    tool_code = orchestrator.request_tool(
        "Hold the 'w' key for a specified duration, then tap 'space' a specified number of times"
    )
    print(tool_code)
