import logging
from google import genai
from google.genai import types
from src.config import GEMINI_API_KEY
from src.tools.weather import get_current_weather
from src.tools.file_reader import read_local_file
from src.tools.list_dir import list_workspace_files

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Registry mapping tool names to python functions
TOOL_REGISTRY = {
    "get_current_weather": get_current_weather,
    "read_local_file": read_local_file,
    "list_workspace_files": list_workspace_files,
}

def get_client() -> genai.Client:
    """Initialize and return the Google GenAI Client."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set. Please set it in your .env file.")
    return genai.Client(api_key=GEMINI_API_KEY)

def generate_response(prompt: str) -> dict:
    """
    Sends a prompt to Gemini, handles the execution of requested tools in a manual loop,
    and returns the final text response along with a log of executed tools.
    
    Args:
        prompt: The user query.
        
    Returns:
        A dict containing 'response' (str) and 'execution_log' (list of dicts).
    """
    client = get_client()
    
    # We pass our functions to tools. The SDK extracts type annotations and docstrings.
    tools_list = list(TOOL_REGISTRY.values())
    
    # Create the chat session
    chat = client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            tools=tools_list,
            temperature=0.2,
            system_instruction=(
                "You are MILO, a highly advanced personal assistant. "
                "You have access to tools for listing files, reading files, and checking the weather. "
                "Always check the files in the workspace using list_workspace_files if the user asks "
                "about project files, configuration, or plans."
            )
        )
    )
    
    execution_log = []
    
    # Send initial user prompt
    response = chat.send_message(prompt)
    
    max_turns = 10
    turns = 0
    
    while turns < max_turns:
        # Check if the response contains any function calls
        if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
            break
            
        function_call = None
        for part in response.candidates[0].content.parts:
            if part.function_call:
                function_call = part.function_call
                break
                
        if not function_call:
            # No tool call requested, this is the final response
            break
            
        fn_name = function_call.name
        fn_args = function_call.args
        
        logger.info(f"Model requested tool call: {fn_name} with args: {fn_args}")
        execution_log.append({"tool": fn_name, "args": dict(fn_args) if fn_args else {}})
        
        # Execute the tool
        if fn_name in TOOL_REGISTRY:
            try:
                # Call the registered function with model-provided arguments
                result_value = TOOL_REGISTRY[fn_name](**fn_args)
                result = {"result": result_value}
            except Exception as e:
                logger.error(f"Error executing tool {fn_name}: {e}")
                result = {"error": str(e)}
        else:
            result = {"error": f"Tool '{fn_name}' is not registered."}
            
        # Send the function response back to the chat session to proceed
        response = chat.send_message(
            types.Part.from_function_response(
                name=fn_name,
                response=result
            )
        )
        turns += 1
        
    return {
        "response": response.text if response.text else "No text response generated.",
        "execution_log": execution_log
    }
