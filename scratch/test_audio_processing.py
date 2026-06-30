import sys
import os
import logging
import subprocess
from gtts import gTTS

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.services.gemini_service import generate_audio_response

logging.basicConfig(level=logging.INFO)

# 1. Generate speech using gTTS (outputs MP3)
mp3_path = "scratch/speech_test.mp3"
print("Generating speech MP3...")
tts = gTTS(text="hola cómo estás", lang='es')
tts.save(mp3_path)

# 2. Convert MP3 to WebM using local ffmpeg
webm_path = "scratch/speech_test.webm"
print("Converting MP3 to WebM...")
ffmpeg_bin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".venv", "bin", "ffmpeg")
if not os.path.exists(ffmpeg_bin):
    ffmpeg_bin = "ffmpeg"

subprocess.run([ffmpeg_bin, "-y", "-i", mp3_path, "-c:a", "libopus", webm_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if not os.path.exists(webm_path):
    print("Error converting speech test MP3 to WebM!")
    sys.exit(1)

# 3. Read WebM and test generate_audio_response
with open(webm_path, "rb") as f:
    audio_bytes = f.read()

print(f"Testing generate_audio_response with {len(audio_bytes)} bytes of speech WebM...")
try:
    result = generate_audio_response(audio_bytes, "audio/webm")
    print("Result:", result)
except Exception as e:
    print("Caught Exception:", e)

# Clean up
if os.path.exists(mp3_path):
    os.remove(mp3_path)
if os.path.exists(webm_path):
    os.remove(webm_path)
