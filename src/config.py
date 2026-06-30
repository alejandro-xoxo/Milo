import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).resolve().parent.parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Log or validate settings
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY is not set. The Gemini service will not function.")
if not ANTHROPIC_API_KEY:
    print("WARNING: ANTHROPIC_API_KEY is not set. Claude fallback will not function.")


