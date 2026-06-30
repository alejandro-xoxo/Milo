import logging
import os
from google import genai
from google.genai import types
from anthropic import Anthropic

from src.config import GEMINI_API_KEY, ANTHROPIC_API_KEY
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

# Define the JSON schemas for Claude (Anthropic requires strict JSON schema)
CLAUDE_TOOLS = [
    {
        "name": "get_current_weather",
        "description": "Get the current weather forecast for a given location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state/country, e.g., 'San Francisco, CA' or 'Madrid, Spain'."
                }
            },
            "required": ["location"]
        }
    },
    {
        "name": "read_local_file",
        "description": "Read the contents of a local text file within the project workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "The relative path to the file from the workspace root (e.g. 'MILO_plan.md' or 'src/config.py')."
                }
            },
            "required": ["filename"]
        }
    },
    {
        "name": "list_workspace_files",
        "description": "List all non-ignored files and folders recursively in the project workspace.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]

def get_gemini_client() -> genai.Client:
    """Initialize and return the Google GenAI Client."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set.")
    return genai.Client(api_key=GEMINI_API_KEY)

def generate_gemini_response(prompt: str) -> dict:
    """Queries Gemini 2.5 Flash with custom tools in a loop."""
    client = get_gemini_client()
    tools_list = list(TOOL_REGISTRY.values())
    
    chat = client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            tools=tools_list,
            temperature=0.2,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            system_instruction=(
                "You are MILO, a highly advanced personal assistant. "
                "You have access to tools for listing files, reading files, and checking the weather. "
                "Always check the files in the workspace using list_workspace_files if the user asks "
                "about project files, configuration, or plans."
            )
        )
    )
    
    execution_log = []
    response = chat.send_message(prompt)
    max_turns = 10
    turns = 0
    
    while turns < max_turns:
        if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
            break
            
        function_call = None
        for part in response.candidates[0].content.parts:
            if part.function_call:
                function_call = part.function_call
                break
                
        if not function_call:
            break
            
        fn_name = function_call.name
        fn_args = function_call.args
        
        logger.info(f"[Gemini] Executing tool: {fn_name} with args: {fn_args}")
        execution_log.append({"tool": fn_name, "args": dict(fn_args) if fn_args else {}})
        
        if fn_name in TOOL_REGISTRY:
            from src.services.circuit_breaker import execute_tool_with_resilience
            result_value = execute_tool_with_resilience(fn_name, TOOL_REGISTRY[fn_name], **fn_args)
            result = {"result": result_value}
        else:
            result = {"error": f"Tool '{fn_name}' is not registered."}
            
        response = chat.send_message(
            types.Part.from_function_response(
                name=fn_name,
                response=result
            )
        )
        turns += 1
        
    return {
        "response": response.text if response.text else "No text response generated.",
        "execution_log": execution_log,
        "provider": "gemini"
    }

def generate_claude_response(prompt: str) -> dict:
    """Queries Claude 3.5 Sonnet with custom tools in a loop."""
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set.")
        
    logger.info("Initializing Claude client...")
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    
    messages = [
        {"role": "user", "content": prompt}
    ]
    
    execution_log = []
    max_turns = 10
    turns = 0
    
    while turns < max_turns:
        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=4000,
            system=(
                "You are MILO, a highly advanced personal assistant. "
                "You have access to tools for listing files, reading files, and checking the weather. "
                "Always check the files in the workspace using list_workspace_files if the user asks "
                "about project files, configuration, or plans."
            ),
            tools=CLAUDE_TOOLS,
            messages=messages,
            temperature=0.2
        )
        
        # Look for tool use blocks in the assistant response
        tool_uses = [block for block in response.content if block.type == "tool_use"]
        
        if not tool_uses:
            text_blocks = [block.text for block in response.content if block.type == "text"]
            final_text = "\n".join(text_blocks)
            return {
                "response": final_text,
                "execution_log": execution_log,
                "provider": "claude"
            }
            
        # Record the assistant response containing tool uses in the messages history
        assistant_content = []
        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input
                })
        messages.append({"role": "assistant", "content": assistant_content})
        
        # Execute each requested tool and format the response blocks
        tool_results_content = []
        for tool_use in tool_uses:
            fn_name = tool_use.name
            fn_args = tool_use.input
            tool_use_id = tool_use.id
            
            logger.info(f"[Claude] Executing tool: {fn_name} with args: {fn_args}")
            execution_log.append({"tool": fn_name, "args": dict(fn_args) if fn_args else {}})
            
            if fn_name in TOOL_REGISTRY:
                from src.services.circuit_breaker import execute_tool_with_resilience
                result_value = execute_tool_with_resilience(fn_name, TOOL_REGISTRY[fn_name], **fn_args)
            else:
                result_value = f"Error: Tool '{fn_name}' is not registered."
                
            tool_results_content.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": result_value
            })
            
        # Append the tool execution results to messages history as a user turn
        messages.append({"role": "user", "content": tool_results_content})
        turns += 1
        
    text_blocks = [block.text for block in response.content if block.type == "text"]
    return {
        "response": "\n".join(text_blocks) or "Exceeded maximum tool execution turns.",
        "execution_log": execution_log,
        "provider": "claude"
    }

def generate_response(prompt: str) -> dict:
    """
    Tries to generate a response using Gemini first. If a limit/quota error
    occurs, falls back to Claude 3.5 Sonnet automatically.
    """
    try:
        logger.info("Attempting generation with Gemini (gemini-2.5-flash)...")
        return generate_gemini_response(prompt)
    except Exception as e:
        error_msg = str(e).lower()
        # Detect common API quota errors
        is_quota_error = any(kw in error_msg for kw in ["quota", "limit", "429", "exhausted"])
        
        if is_quota_error or not GEMINI_API_KEY:
            logger.warning(f"Gemini API quota/availability issue: {e}. Switching to Claude 3.5 Sonnet...")
            try:
                return generate_claude_response(prompt)
            except Exception as claude_err:
                logger.error(f"Claude fallback failed: {claude_err}")
                raise RuntimeError(
                    f"Both Gemini and Claude fallback failed.\nGemini Error: {e}\nClaude Error: {claude_err}"
                )
        else:
            logger.error(f"Gemini encountered a non-quota error: {e}")
            raise e

def generate_audio_response(audio_bytes: bytes, mime_type: str = "audio/wav") -> dict:
    """
    Sends an audio command to Gemini with custom tools, handles tool calls in a loop,
    and returns the final response and tool execution log.
    """
    client = get_gemini_client()
    tools_list = list(TOOL_REGISTRY.values())
    
    chat = client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            tools=tools_list,
            temperature=0.3,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            system_instruction=(
                "You are MILO, a highly advanced personal assistant. "
                "You have access to tools for listing files, reading files, and checking the weather. "
                "Always check the files in the workspace using list_workspace_files if the user asks "
                "about project files, configuration, or plans. "
                "You are receiving a voice prompt. Answer in a natural, conversational way in Spanish. "
                "Your text response will be converted to speech automatically, so speak directly "
                "as if you are speaking to the user. Never say you cannot speak or use voice."
            )
        )
    )
    
    execution_log = []
    
    # Construct the audio part
    audio_part = types.Part.from_bytes(
        data=audio_bytes,
        mime_type=mime_type
    )
    
    # Send the audio part with a text instruction to force Spanish conversational response
    response = chat.send_message(
        [
            audio_part,
            "Responde de forma directa al comando de voz anterior en español."
        ]
    )
    
    max_turns = 10
    turns = 0
    
    while turns < max_turns:
        if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
            break
            
        function_call = None
        for part in response.candidates[0].content.parts:
            if part.function_call:
                function_call = part.function_call
                break
                
        if not function_call:
            break
            
        fn_name = function_call.name
        fn_args = function_call.args
        
        logger.info(f"[Gemini Audio] Executing tool: {fn_name} with args: {fn_args}")
        execution_log.append({"tool": fn_name, "args": dict(fn_args) if fn_args else {}})
        
        if fn_name in TOOL_REGISTRY:
            from src.services.circuit_breaker import execute_tool_with_resilience
            result_value = execute_tool_with_resilience(fn_name, TOOL_REGISTRY[fn_name], **fn_args)
            result = {"result": result_value}
        else:
            result = {"error": f"Tool '{fn_name}' is not registered."}
            
        response = chat.send_message(
            types.Part.from_function_response(
                name=fn_name,
                response=result
            )
        )
        turns += 1
        
    return {
        "response": response.text if response.text else "No he podido generar una respuesta de voz.",
        "execution_log": execution_log,
        "provider": "gemini"
    }

