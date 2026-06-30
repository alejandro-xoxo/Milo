import sys
import httpx
import subprocess
import os
from gtts import gTTS

def speak(text: str):
    """Sintetiza la respuesta en audio y la reproduce."""
    try:
        import re
        clean_text = re.sub(r'```.*?```', '[Detalles del archivo en pantalla]', text, flags=re.DOTALL)
        clean_text = re.sub(r'[*#_`-]', '', clean_text)
        
        tts = gTTS(text=clean_text, lang="es", slow=False)
        temp_mp3 = "response.mp3"
        tts.save(temp_mp3)
        
        players = ["mpg123", "mpv", "play", "aplay", "paplay"]
        played = False
        
        for player in players:
            try:
                subprocess.run([player, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if player in ["aplay", "paplay"]:
                    try:
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
                    subprocess.run([player, temp_mp3], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    played = True
                    break
            except FileNotFoundError:
                continue
                
        if os.path.exists(temp_mp3):
            os.remove(temp_mp3)
            
    except Exception as e:
        print(f"Error al reproducir audio de respuesta: {e}")

def main():
    if len(sys.argv) < 2:
        print("Uso: python src/client.py \"<tu prompt aquí>\"")
        sys.exit(1)
        
    prompt = sys.argv[1]
    url = "http://localhost:8000/chat"
    
    print(f"🚀 Enviando prompt a MILO: '{prompt}'...")
    try:
        response = httpx.post(url, json={"prompt": prompt}, timeout=60.0)
        if response.status_code == 200:
            data = response.json()
            print("\n✨ === RESPUESTA DE MILO === ✨")
            print(data["response"])
            
            # Speak the response out loud
            speak(data["response"])
            
            print("\n🔧 === HERRAMIENTAS EJECUTADAS === 🔧")
            if data["execution_log"]:
                for log in data["execution_log"]:
                    print(f"👉 Herramienta: {log['tool']} | Args: {log['args']}")
            else:
                print("Ninguna (Gemini respondió directamente sin usar herramientas)")
        else:
            print(f"\n❌ Error ({response.status_code}): {response.text}")
    except httpx.RequestError as exc:
        print(f"\n❌ Error de conexión al servidor: {exc}")
        print("💡 Consejo: Asegúrate de que el servidor FastAPI esté corriendo con: python -m src.main")

if __name__ == "__main__":
    main()
