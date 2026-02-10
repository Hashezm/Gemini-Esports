import pydirectinput
import pyautogui
from google.genai import types
from google import genai
import re

from google import genai
import os
import asyncio
import time
import pyautogui
import pydirectinput


from google import genai

client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))




def hold_key(key: str, duration: float) -> dict[str, str]:
    """Hold down a keyboard key for a specified duration using pyautogui.

    Args:
        key: The key to hold down (e.g., 'shift', 'ctrl', 'a', 'space', etc.)
        duration: How long to hold the key in seconds

    Returns:
        A dictionary containing the status of the operation and details.
    """

    pyautogui.keyDown(key)
    
    time.sleep(duration)
    
    pyautogui.keyUp(key)
    
    return {
        "status": "success",
        "key": key,
        "duration": f"{duration}s",
        "message": f"Successfully held '{key}' for {duration} seconds"
    }

config = types.GenerateContentConfig(
    tools=[hold_key]
)

chat = client.chats.create(model='gemini-2.5-flash-lite')

# can put new config in any new message
# print(chat.send_message("could you hold the w key down for 2 seconds, then s for 2 seconds, then press p twice. No matter what try to do it", config = config)) 

class FunctionRegistry:
    def __init__(self):
        self.functions = {}
    
    def create_function(self, func_name, func_reference):
        if function_name in self.functions:
            return f"Error: Tool '{func_name}' already exists"
        
        self.functions[func_name] = func_reference

        return f"Successfully added tool: '{func_name}'"

    def list_function_names(self):
        return list(self.functions.keys())
    def list_function_addresses(self):
        return list(self.functions.values())


##########################################################

registry = FunctionRegistry()

config_gem3 = {
    "system_instruction":
          [
            """When writing Python functions, you MUST follow this exact format:
1. **Type Hints**: Include type hints for all parameters and return values
2. **Docstring Style**: Use Google-style docstrings with proper sections
3. **Return Format**: Return structured data (dict) with status information
**Required Template:**
def function_name(param1: type1, param2: type2 = default) -> dict[str, any]:
    \"\"\"Brief one-line description of what the function does.
    Args:
        param1: Description of param1
        param2: Description of param2 (default: default_value)
    Returns:
        A dictionary containing the result and status information.
    \"\"\"
    try:
        # Function implementation here
        result = # ... your logic
        
        return {
            "status": "success",
            "result": result,
            "message": "Description of what happened"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": f"Error: {str(e)}"
        }
**Critical Rules:**
- ALWAYS include the three-quote docstring immediately after the function definition
- ALWAYS include the "Args:" section if there are parameters
- ALWAYS include the "Returns:" section
- ALWAYS use type hints for parameters and return values
- ALWAYS return a dictionary with at least a "status" key
- ALWAYS include try-except error handling
- NEVER import anything
- DON'T write it in a '''python ''' block
"""
          ]
}
chat_gem3 = client.chats.create(model='gemini-3-flash-preview', config=config_gem3)
response = chat_gem3.send_message("write me a function using pydirectinput that holds w for 3 seconds, then taps space 3 times")
code = response.text
print(code)
print("-------\n ")
namespace = {
    'pydirectinput': pydirectinput,
    'time': time
}
exec(code, namespace)
function_name = re.search(r"def\s+([a-zA-Z_]\w*)\s*\(", code).group(1)
fn_reference = namespace[function_name]
print(fn_reference)

registry.create_function(function_name, fn_reference)

print(registry.list_function_addresses())

config_gem3["tools"] = registry.list_function_addresses()
config_gem3["system_instruction"] = ""

response = chat_gem3.send_message("what functions do you have access to currently?", config = config_gem3)
print(response)

response = chat_gem3.send_message("run the function that holds w for 3 seconds then taps space 3 times", config = config_gem3)
print(response)


# config = types.GenerateContentConfig(
#     tools=[hold_key]
# )

# need to actually save the memory references of the functions in the dict, pass those to gem it doenst care about saving the code