import os
import sys

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["DB_PATH"] = "test_milo.db"

from src.services.db_service import init_db, add_chat_message
from src.services.agy_brain import AgyBrain

# Initialize database and add some messages to exceed threshold and trigger summarization
init_db()
# Let's add 10 user/assistant messages to force get_optimized_context to call _summarize_text
for i in range(10):
    add_chat_message("default", "user", f"Mensaje del usuario {i}")
    add_chat_message("default", "assistant", f"Respuesta de MILO {i}")

brain = AgyBrain(".")
print("Enviando mensaje para probar recursión...")
try:
    brain.ask("hola")
except Exception as e:
    import traceback
    traceback.print_exc()
