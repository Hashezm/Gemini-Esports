"""
Dynamic Tool-Writing System with Gemini Live API

A system where Gemini can use tools AND dynamically create new tools at runtime.
Uses session resumption to reload with updated tools without losing context.
"""

import asyncio
import time
from datetime import datetime
from typing import Callable, Any
from google import genai
from google.genai import types
from dotenv import load_dotenv
import pyautogui

load_dotenv()

MODEL_NAME = 'gemini-2.0-flash-exp'


class ToolRegistry:
    """Manages available tools dynamically."""
    
    def __init__(self):
        self.tools: dict[str, dict] = {}  # name -> {fn, description, parameters}
    
    def register(self, name: str, fn: Callable, description: str, parameters: dict[str, str] = None):
        """Register a tool in the registry."""
        self.tools[name] = {
            "fn": fn,
            "description": description,
            "parameters": parameters or {}
        }
        print(f"[ToolRegistry] Registered tool: {name}")
    
    def call(self, tool_name: str, args: dict) -> Any:
        """Execute a tool by name."""
        if tool_name not in self.tools:
            return f"Error: Tool '{tool_name}' not found"
        try:
            result = self.tools[tool_name]["fn"](**args)
            return result
        except Exception as e:
            return f"Error executing tool '{tool_name}': {e}"
    
    def get_tool_declarations(self) -> list:
        """Get tool declarations for Gemini API."""
        declarations = []
        for name, info in self.tools.items():
            params = info.get("parameters", {})
            
            # Check if parameters is already a full JSON Schema (has 'properties' key)
            if isinstance(params, dict) and "properties" in params:
                # It's already a full schema, use it directly
                schema = {
                    "type": "OBJECT",
                    "properties": {},
                }
                # Extract and normalize the properties
                for prop_name, prop_def in params.get("properties", {}).items():
                    prop_type = prop_def.get("type", "string").upper()
                    schema["properties"][prop_name] = {
                        "type": prop_type,
                        "description": prop_def.get("description", "")
                    }
                if params.get("required"):
                    schema["required"] = params["required"]
            else:
                # Simple {name: type} format - build the schema
                properties = {}
                required = []
                for param_name, param_type in params.items():
                    # Normalize type names to uppercase
                    normalized_type = param_type.upper() if isinstance(param_type, str) else "STRING"
                    properties[param_name] = {"type": normalized_type}
                    required.append(param_name)
                
                schema = {
                    "type": "OBJECT",
                    "properties": properties,
                    "required": required
                } if properties else None
            
            decl = types.FunctionDeclaration(
                name=name,
                description=info["description"],
                parameters=schema
            )
            declarations.append(decl)
        return declarations
    
    def list_all(self) -> str:
        """List all registered tools."""
        if not self.tools:
            return "No tools registered."
        lines = ["Available tools:"]
        for name, info in self.tools.items():
            params = ", ".join(f"{k}: {v}" for k, v in info["parameters"].items())
            lines.append(f"  - {name}({params}): {info['description']}")
        return "\n".join(lines)


# Global registry
registry = ToolRegistry()

# Global state for session resumption
resumption_token: str | None = None
needs_reconnect = False


# ============ PREDEFINED TOOLS ============

def get_current_time() -> str:
    """Returns the current date and time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def list_tools() -> str:
    """Lists all available tools."""
    return registry.list_all()


def create_tool(name: str, description: str, parameters_json: str, code: str) -> str:
    """
    Creates a new tool from Python code. After creation, the session will 
    reconnect to make the new tool available.
    
    Args:
        name: Tool name (e.g., "convert_temperature")  
        description: What the tool does
        parameters_json: JSON string of parameters, e.g. '{"celsius": "number"}'
        code: Python function body as a string. Must define a function with the same name.
              Example: 'def convert_temperature(celsius):\\n    return celsius * 9/5 + 32'
    
    Returns:
        Success message or error
    """
    global needs_reconnect
    
    import json
    
    # Parse parameters
    try:
        parameters = json.loads(parameters_json)
    except json.JSONDecodeError as e:
        return f"Error parsing parameters_json: {e}"
    
    # Validate name
    if not name.isidentifier():
        return f"Error: '{name}' is not a valid Python identifier"
    
    if name in registry.tools:
        return f"Error: Tool '{name}' already exists"
    
    # Try to compile and execute the code
    try:
        # Create a namespace for the function
        namespace = {
            'pyautogui': pyautogui
        }
        exec(code, namespace)
        
        # Check if the function was defined
        if name not in namespace:
            return f"Error: Code must define a function named '{name}'"
        
        fn = namespace[name]
        if not callable(fn):
            return f"Error: '{name}' is not callable"
        
        # Register the new tool
        registry.register(name, fn, description, parameters)
        
        # Trigger reconnection
        needs_reconnect = True
        
        return f"Success! Tool '{name}' created. Session will reconnect to activate it."
        
    except SyntaxError as e:
        return f"Syntax error in code: {e}"
    except Exception as e:
        return f"Error creating tool: {e}"


# Register predefined tools
def register_default_tools():
    registry.register(
        "get_current_time",
        get_current_time,
        "Returns the current date and time",
        {}
    )

    registry.register(
        "list_tools",
        list_tools,
        "Lists all available tools",
        {}
    )
    registry.register(
        "create_tool",
        create_tool,
        "Creates a new tool from Python code. The session will reconnect after creation to make it available.",
        {
            "name": "string",
            "description": "string",
            "parameters_json": "string",
            "code": "string"
        }
    )


# ============ SESSION MANAGEMENT ============

def get_config():
    """Build the session configuration with current tools."""
    return types.LiveConnectConfig(
        response_modalities=["TEXT"],
        session_resumption=types.SessionResumptionConfig(
            handle=resumption_token  # None for new session, token for resume
        ),
        tools=[types.Tool(function_declarations=registry.get_tool_declarations())]
    )


async def handle_tool_call(session, tool_call):
    """Process a function call from the model."""
    for fc in tool_call.function_calls:
        print(f"\n[Tool Call] {fc.name}({fc.args})")
        
        # Execute the tool
        result = registry.call(fc.name, fc.args)
        print(f"[Tool Result] {result}")
        
        # Send result back to model
        await session.send_tool_response(
            function_responses=[types.FunctionResponse(
                name=fc.name,
                id=fc.id,
                response={"result": str(result)}
            )]
        )


async def handle_responses(session):
    """Handle all responses from the model."""
    global resumption_token
    
    while True:
        try:
            turn = session.receive()
            async for response in turn:
                # Check for session resumption update
                if hasattr(response, 'session_resumption_update') and response.session_resumption_update:
                    update = response.session_resumption_update
                    if update.resumable and update.new_handle:
                        resumption_token = update.new_handle
                        # print(f"\n[Session] Got resumption token: {resumption_token[:20]}...")
                
                # Handle tool calls
                if response.tool_call:
                    await handle_tool_call(session, response.tool_call)
                
                # Handle text
                if text := response.text:
                    print(text, end="", flush=True)
                
                # Check turn complete
                if response.server_content and response.server_content.turn_complete:
                    print()  # Newline after turn
                    
        except asyncio.CancelledError:
            return


async def send_text(session):
    """Handle user input."""
    global needs_reconnect
    
    while True:
        text = await asyncio.to_thread(input, "\nYou > ")
        
        if text.lower() == "q":
            return "quit"
        
        if text.lower() == "tools":
            print(registry.list_all())
            continue
        
        # Send to model
        await session.send_client_content(
            turns=[types.Content(role="user", parts=[types.Part(text=text)])]
        )
        
        # Small delay to let response start
        await asyncio.sleep(0.5)
        
        # Check if we need to reconnect (after tool creation)
        if needs_reconnect:
            needs_reconnect = False
            return "reconnect"


async def run_session():
    """Run a single session, returns reason for exit."""
    global resumption_token
    
    client = genai.Client(http_options={"api_version": "v1alpha"})
    
    config = get_config()
    if resumption_token:
        print(f"\n[Session] Resuming with token...")
    else:
        print("\n[Session] Starting new session...")
    
    async with client.aio.live.connect(model=MODEL_NAME, config=config) as session:
        print("[Session] Connected!")
        print("Type your message, 'tools' to list tools, or 'q' to quit.\n")
        
        # Start response handler
        response_task = asyncio.create_task(handle_responses(session))
        
        # Handle user input
        exit_reason = await send_text(session)
        
        # Cleanup
        response_task.cancel()
        try:
            await response_task
        except asyncio.CancelledError:
            pass
        
        return exit_reason


async def main():
    """Main entry point with session resumption loop."""
    print("=" * 50)
    print("  Dynamic Tool-Writing System")
    print("  Gemini can create its own tools!")
    print("=" * 50)
    
    # Register default tools
    register_default_tools()
    
    while True:
        exit_reason = await run_session()
        
        if exit_reason == "quit":
            print("\nGoodbye!")
            break
        elif exit_reason == "reconnect":
            print("\n[Session] Reconnecting with updated tools...")
            # Loop continues, will reconnect with resumption token


if __name__ == "__main__":
    asyncio.run(main())
