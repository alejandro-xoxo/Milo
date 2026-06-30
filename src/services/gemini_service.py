import logging
import os
import re
import ast

from src.tools.weather import get_current_weather
from src.tools.file_reader import read_local_file
from src.tools.list_dir import list_workspace_files
from src.tools.web_search import web_search
from src.tools.web_fetcher import fetch_page
from src.tools.antigravity import run_antigravity
from src.services.agy_brain import AgyBrain
from src.services.circuit_breaker import execute_tool_with_resilience

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOOL_REGISTRY = {
    "get_current_weather": get_current_weather,
    "read_local_file": read_local_file,
    "list_workspace_files": list_workspace_files,
    "web_search": web_search,
    "fetch_page": fetch_page,
    "run_antigravity": run_antigravity,
}

SYSTEM_CONTEXT = """
Eres el motor de razonamiento de MILO. Si necesitas usar una herramienta,
responde EXACTAMENTE así:
TOOL_CALL: nombre_herramienta(parametro="valor")

Herramientas disponibles:
- get_current_weather(location: str)
- read_local_file(filename: str)
- list_workspace_files()
- web_search(query: str, num_results: int)
- fetch_page(url: str, max_chars: int)
- run_antigravity(task: str, mode: str)
"""

def parse_tool_call(response_text: str):
    match = re.search(r"TOOL_CALL:\s*([a-zA-Z0-9_]+)\((.*)\)", response_text)
    if not match:
        return None, None
    fn_name = match.group(1)
    args_str = match.group(2)
    kwargs = {}
    if args_str.strip():
        try:
            parsed = ast.parse(f"f({args_str})")
            for keyword in parsed.body[0].value.keywords:
                kwargs[keyword.arg] = ast.literal_eval(keyword.value)
        except Exception as e:
            logger.error(f"Error parsing args: {e}")
            pass
    return fn_name, kwargs

def generate_response(prompt: str) -> dict:
    project_path = os.getcwd()
    brain = AgyBrain(project_path)
    
    full_prompt = SYSTEM_CONTEXT + f"\nUsuario: {prompt}"
    execution_log = []
    
    max_turns = 10
    turns = 0
    
    current_prompt = full_prompt
    response_text = ""
    while turns < max_turns:
        response_text = brain.ask(current_prompt, mode="chat")
        
        fn_name, fn_args = parse_tool_call(response_text)
        
        if fn_name:
            logger.info(f"[AgyBrain] Executing tool: {fn_name} with args: {fn_args}")
            execution_log.append({"tool": fn_name, "args": fn_args})
            
            if fn_name in TOOL_REGISTRY:
                try:
                    result_value = execute_tool_with_resilience(fn_name, TOOL_REGISTRY[fn_name], **fn_args)
                except Exception as e:
                    result_value = f"Error executing tool: {e}"
            else:
                result_value = f"Error: Tool '{fn_name}' is not registered."
                
            current_prompt = f"Resultado de la herramienta {fn_name}: {result_value}\nResponde al usuario o haz otra llamada a herramienta."
            turns += 1
        else:
            return {
                "response": response_text,
                "execution_log": execution_log,
                "provider": "agy"
            }
            
    return {
        "response": response_text,
        "execution_log": execution_log,
        "provider": "agy"
    }

def generate_audio_response(audio_bytes: bytes, mime_type: str = "audio/wav") -> dict:
    import speech_recognition as sr
    import tempfile
    import subprocess
    
    recognizer = sr.Recognizer()
    text = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp_in:
            tmp_in.write(audio_bytes)
            tmp_in_name = tmp_in.name
            
        tmp_wav_name = tmp_in_name + ".wav"
        
        # Use the locally installed static ffmpeg binary to ensure it's found without relying on PATH
        ffmpeg_bin = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".venv", "bin", "ffmpeg")
        if not os.path.exists(ffmpeg_bin):
            ffmpeg_bin = "ffmpeg" # Fallback a PATH normal si no está en el venv

        subprocess.run([ffmpeg_bin, "-y", "-i", tmp_in_name, "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", tmp_wav_name], 
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if os.path.exists(tmp_wav_name):
            with sr.AudioFile(tmp_wav_name) as source:
                audio_data = recognizer.record(source)
                try:
                    text = recognizer.recognize_google(audio_data, language="es-ES")
                    logger.info(f"Transcripción exitosa: {text}")
                except sr.UnknownValueError:
                    text = "No pude entender el audio."
                except sr.RequestError as e:
                    text = f"Error en el servicio de reconocimiento: {e}"
        else:
            text = "Error al convertir el audio a WAV."
            
        if os.path.exists(tmp_in_name):
            os.remove(tmp_in_name)
        if os.path.exists(tmp_wav_name):
            os.remove(tmp_wav_name)
            
    except Exception as e:
        logger.error(f"Error procesando audio: {e}")
        text = f"Ocurrió un error al procesar el audio: {e}"

    if not text.strip() or text.startswith("Error") or text.startswith("No pude"):
        return {"response": text, "execution_log": [], "provider": "agy"}
        
    return generate_response(text)
