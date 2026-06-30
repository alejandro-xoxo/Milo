import os
import sys
import time
import httpx
import sounddevice as sd
import soundfile as sf
import subprocess
from gtts import gTTS

# Fallback mechanism if pynput fails (e.g., no GUI display or missing libraries)
try:
    from pynput import keyboard
    has_pynput = True
except Exception:
    has_pynput = False

SAMPLE_RATE = 16000
CHANNELS = 1
AUDIO_FILE = "query.wav"
API_URL = "http://localhost:8000/chat/audio"

class AudioRecorder:
    def __init__(self):
        self.recording = False
        self.stream = None
        self.audio_data = []

    def callback(self, indata, frames, time_info, status):
        if status:
            print(status, file=sys.stderr)
        if self.recording:
            self.audio_data.append(indata.copy())

    def start_recording(self):
        self.audio_data = []
        self.recording = True
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype='int16',
            callback=self.callback
        )
        self.stream.start()
        print("\n🔴 MILO está escuchando... Habla ahora.")

    def stop_recording(self) -> str:
        self.recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        print("⏹️ Grabación detenida. Procesando audio...")
        
        if not self.audio_data:
            print("❌ No se detectó audio.")
            return None
        
        import numpy as np
        audio_np = np.concatenate(self.audio_data, axis=0)
        sf.write(AUDIO_FILE, audio_np, SAMPLE_RATE)
        return AUDIO_FILE

    def process_audio(self, file_path: str):
        if not file_path or not os.path.exists(file_path):
            return
            
        print("🚀 Enviando comando de voz a MILO...")
        try:
            with open(file_path, "rb") as f:
                files = {"file": (file_path, f, "audio/wav")}
                response = httpx.post(API_URL, files=files, timeout=60.0)
                
            if response.status_code == 200:
                data = response.json()
                text_response = data["response"]
                execution_log = data["execution_log"]
                
                print("\n✨ === RESPUESTA DE MILO === ✨")
                print(text_response)
                
                if execution_log:
                    print("\n🔧 Herramientas ejecutadas:")
                    for log in execution_log:
                        print(f"👉 {log['tool']} ({log['args']})")
                
                speak(text_response)
            else:
                print(f"\n❌ Error en el servidor MILO ({response.status_code}): {response.text}")
        except Exception as e:
            print(f"\n❌ Error al conectar con MILO: {e}")
        finally:
            if os.path.exists(AUDIO_FILE):
                os.remove(AUDIO_FILE)

def speak(text: str):
    """Sintetiza la respuesta en audio y la reproduce usando un comando del sistema."""
    try:
        # Limpiar markdown de código para evitar que el lector deletree símbolos extraños
        import re
        clean_text = re.sub(r'```.*?```', '[Detalles del archivo en pantalla]', text, flags=re.DOTALL)
        clean_text = re.sub(r'[*#_`-]', '', clean_text)
        
        tts = gTTS(text=clean_text, lang="es", slow=False)
        temp_mp3 = "response.mp3"
        tts.save(temp_mp3)
        
        # Reproductores de audio comunes en Linux
        players = ["mpg123", "mpv", "play", "aplay", "paplay"]
        played = False
        
        for player in players:
            try:
                # Comprobar si el reproductor está instalado
                subprocess.run([player, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if player in ["aplay", "paplay"]:
                    try:
                        # Convertir a WAV primero con ffmpeg si es necesario
                        ffmpeg_bin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".venv", "bin", "ffmpeg")
                        if not os.path.exists(ffmpeg_bin): ffmpeg_bin = "ffmpeg"
                        subprocess.run([ffmpeg_bin, "-y", "-i", temp_mp3, "response.wav"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        subprocess.run([player, "response.wav"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if os.path.exists("response.wav"):
                            os.remove("response.wav")
                        played = True
                        break
                    except Exception:
                        continue
                else:
                    # Reproducir MP3 directamente con mpg123 / mpv / play
                    subprocess.run([player, temp_mp3], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    played = True
                    break
            except FileNotFoundError:
                continue
                
        if not played:
            print("\n💡 Consejo: Para escuchar la voz de MILO, instala 'mpg123' o 'mpv' en tu terminal (ej: sudo apt install mpg123).")
            
        if os.path.exists(temp_mp3):
            os.remove(temp_mp3)
            
    except Exception as e:
        print(f"Error al reproducir audio de respuesta: {e}")

def run_pynput_mode(recorder: AudioRecorder):
    print("🎙️  MILO MODO DE VOZ ACTIVO (Teclado)")
    print("👉 Presiona la tecla 'm' para EMPEZAR a grabar.")
    print("👉 Presiona la tecla 'm' otra vez para DETENER y enviar.")
    print("Presiona Ctrl+C para salir.")
    
    def on_press(key):
        try:
            if hasattr(key, 'char') and key.char == 'm':
                if not recorder.recording:
                    recorder.start_recording()
                else:
                    file_path = recorder.stop_recording()
                    recorder.process_audio(file_path)
        except Exception:
            pass

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()

def run_fallback_mode(recorder: AudioRecorder):
    print("🎙️  MILO MODO DE VOZ ACTIVO (Consola)")
    print("👉 Presiona ENTER para EMPEZAR a grabar.")
    print("👉 Presiona ENTER de nuevo para DETENER y enviar.")
    print("Presiona Ctrl+C para salir.")
    
    while True:
        try:
            input("\n[Presiona ENTER para empezar]")
            recorder.start_recording()
            input("[Presiona ENTER para detener]")
            file_path = recorder.stop_recording()
            recorder.process_audio(file_path)
        except (KeyboardInterrupt, SystemExit):
            print("\nSaliendo del cliente de voz...")
            break

def main():
    recorder = AudioRecorder()
    
    # Si tenemos pynput y hay una sesión gráfica activa (DISPLAY), usamos teclado
    if has_pynput and os.getenv("DISPLAY"):
        try:
            run_pynput_mode(recorder)
        except Exception as e:
            print(f"Advertencia: No se pudo inicializar captura de teclado ({e}). Usando modo consola.")
            run_fallback_mode(recorder)
    else:
        run_fallback_mode(recorder)

if __name__ == "__main__":
    main()
