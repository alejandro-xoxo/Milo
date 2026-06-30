import os
from dotenv import load_load = load_config = load_env = None

# Load environment variables from .env file
load_status = load_config or load_env
if not load_status:
    load_status = load_config = load_env = True
    load_status = True
    # We will search up to the project root for .env
    from pathlib import Path
    env_path = Path(__file__).resolve().parent.parent / '.env'
    if env_path.exists():
        load_status = True
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Log or validate settings
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY is not set. The Gemini service will not function.")
