import logging
import os
import time
import threading

from src.services.agy_brain import AgyBrain

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_response(prompt: str, status_callback=None) -> dict:
    """
    Delega toda la lógica e inferencia nativa a Antigravity CLI (agy).
    Eliminamos las herramientas redundantes de Python ya que Agy puede usar
    nativamente sus propias herramientas (web_search, read_file, run_command, etc).
    """
    project_path = os.getcwd()
    brain = AgyBrain(project_path)
    
    # Progreso REAL a través de transcript.jsonl
    stop_simulation = threading.Event()
    
    def simulate_progress():
        brain_dir = os.path.expanduser("~/.gemini/antigravity-cli/brain/")
        
        # Encontrar el directorio más reciente (la conversación actual)
        # Hacemos polling los primeros segundos hasta que aparezca
        latest_transcript = None
        for _ in range(10):
            if stop_simulation.is_set():
                break
            try:
                subdirs = [os.path.join(brain_dir, d) for d in os.listdir(brain_dir) if os.path.isdir(os.path.join(brain_dir, d))]
                if subdirs:
                    latest_dir = max(subdirs, key=os.path.getmtime)
                    candidate = os.path.join(latest_dir, ".system_generated", "logs", "transcript.jsonl")
                    if os.path.exists(candidate):
                        # Nos aseguramos que sea reciente
                        if time.time() - os.path.getmtime(candidate) < 10:
                            latest_transcript = candidate
                            break
            except Exception:
                pass
            time.sleep(1)

        if not latest_transcript:
            # Fallback
            if status_callback: status_callback("Pensando...")
            return

        # Tail del archivo
        import json
        try:
            with open(latest_transcript, 'r') as f:
                # Nos movemos al final del archivo actual
                f.seek(0, 2)
                while not stop_simulation.is_set():
                    line = f.readline()
                    if not line:
                        time.sleep(0.5)
                        continue
                    
                    try:
                        data = json.loads(line.strip())
                        if data.get("type") == "PLANNER_RESPONSE" and "tool_calls" in data:
                            tools = data["tool_calls"]
                            for tool in tools:
                                name = tool.get("name")
                                if name == "run_command":
                                    cmd = tool.get("args", {}).get("CommandLine", "")
                                    status_callback(f"Ejecutando: {cmd[:40]}...")
                                elif name == "view_file" or name == "read_file":
                                    path = tool.get("args", {}).get("AbsolutePath", "") or tool.get("args", {}).get("Target", "")
                                    basename = os.path.basename(path) if path else "archivo"
                                    status_callback(f"Leyendo {basename}...")
                                elif name == "search_web":
                                    status_callback("Buscando en la web...")
                                else:
                                    status_callback(f"Usando herramienta {name}...")
                    except Exception:
                        pass
        except Exception:
            pass

    sim_thread = None
    if status_callback:
        sim_thread = threading.Thread(target=simulate_progress)
        sim_thread.start()
    
    try:
        # Aquí Agy hace todo su magia nativa, incluyendo llamadas a herramientas internas.
        response_text = brain.ask(prompt, mode="chat", status_callback=status_callback)
    finally:
        stop_simulation.set()
        if sim_thread:
            sim_thread.join()
            
    if status_callback:
        status_callback("Proceso completado.")

    from src.services.db_service import get_tool_failure_status
    active_engine = get_tool_failure_status("active_engine")["disabled_until"] or "vulcan"

    return {
        "response": response_text,
        "execution_log": [], # Ya no trackeamos herramientas de Python
        "provider": active_engine
    }


def generate_audio_response(audio_bytes: bytes, mime_type: str = "audio/wav", status_callback=None) -> dict:
    import speech_recognition as sr
    import tempfile
    import subprocess
    
    if status_callback:
        status_callback("Procesando audio (Speech-to-Text)...")
        
    recognizer = sr.Recognizer()
    text = ""
    tmp_in_name = None
    tmp_wav_name = None
    
    # Detect container format using magic bytes
    extension = ".webm" # Default fallback
    if audio_bytes and len(audio_bytes) >= 12:
        magic_4 = audio_bytes[:4]
        if magic_4 == b"\x1a\x45\xdf\xa3":
            extension = ".webm"
        elif magic_4 == b"OggS":
            extension = ".ogg"
        elif magic_4 == b"RIFF" and audio_bytes[8:12] == b"WAVE":
            extension = ".wav"
        elif magic_4 == b"ID3" or (magic_4[0] == 0xff and (magic_4[1] & 0xe0) == 0xe0):
            extension = ".mp3"
        elif audio_bytes[4:8] == b"ftyp" or b"ftyp" in audio_bytes[:20]:
            extension = ".m4a"
    elif mime_type:
        mime_lower = mime_type.lower()
        if "audio/mp4" in mime_lower or "audio/m4a" in mime_lower or "video/mp4" in mime_lower:
            extension = ".m4a"
        elif "audio/ogg" in mime_lower or "audio/opus" in mime_lower or "ogg" in mime_lower:
            extension = ".ogg"
        elif "audio/wav" in mime_lower or "audio/x-wav" in mime_lower or "wav" in mime_lower:
            extension = ".wav"
        elif "audio/mpeg" in mime_lower or "audio/mp3" in mime_lower or "mp3" in mime_lower:
            extension = ".mp3"

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp_in:
            tmp_in.write(audio_bytes)
            tmp_in_name = tmp_in.name
            
        tmp_wav_name = tmp_in_name + ".wav"
        
        # Use the locally installed static ffmpeg binary to ensure it's found without relying on PATH
        ffmpeg_bin = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".venv", "bin", "ffmpeg")
        if not os.path.exists(ffmpeg_bin):
            ffmpeg_bin = "ffmpeg" # Fallback a PATH normal si no está en el venv

        # Run ffmpeg and capture output for debugging
        result_ffmpeg = subprocess.run(
            [ffmpeg_bin, "-y", "-i", tmp_in_name, "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", tmp_wav_name], 
            capture_output=True,
            text=True
        )
        
        if result_ffmpeg.returncode != 0:
            logger.error(f"FFmpeg failed with code {result_ffmpeg.returncode}. Stderr: {result_ffmpeg.stderr}")
            text = "Error al convertir el audio a WAV."
        elif os.path.exists(tmp_wav_name) and os.path.getsize(tmp_wav_name) > 0:
            try:
                with sr.AudioFile(tmp_wav_name) as source:
                    audio_data = recognizer.record(source)
                    try:
                        text = recognizer.recognize_google(audio_data, language="es-ES")
                        logger.info(f"Transcripción exitosa: {text}")
                    except sr.UnknownValueError:
                        text = "No pude entender el audio."
                    except sr.RequestError as e:
                        text = f"Error en el servicio de reconocimiento: {e}"
            except Exception as sr_err:
                logger.error(f"Error reading WAV or running speech recognition: {sr_err}")
                text = f"Error al procesar el archivo de audio: {sr_err}"
        else:
            text = "Error al convertir el audio a WAV."
            
    except Exception as e:
        logger.error(f"Error procesando audio: {e}")
        text = f"Ocurrió un error al procesar el audio: {e}"
    finally:
        # Guarantee cleanup of temporary files
        if tmp_in_name and os.path.exists(tmp_in_name):
            try:
                os.remove(tmp_in_name)
            except Exception as err:
                logger.error(f"Failed to remove temp input file: {err}")
        if tmp_wav_name and os.path.exists(tmp_wav_name):
            try:
                os.remove(tmp_wav_name)
            except Exception as err:
                logger.error(f"Failed to remove temp WAV file: {err}")

    if not text.strip() or text.startswith("Error") or text.startswith("No pude"):
        from src.services.db_service import get_tool_failure_status
        active_engine = get_tool_failure_status("active_engine")["disabled_until"] or "vulcan"
        return {"response": text, "execution_log": [], "provider": active_engine}
        
    return generate_response(text, status_callback)
