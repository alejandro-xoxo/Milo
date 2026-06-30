from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import os
import io
from gtts import gTTS
from pydantic import BaseModel
from src.services.gemini_service import generate_response
from src.config import HOST, PORT
from src.services.db_service import init_db
from src.services.queue_runner import init_runner, stop_runner

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database
    init_db()
    # Start the background task queue runner
    init_runner()
    yield
    # Stop the background task queue runner on shutdown
    stop_runner()

app = FastAPI(
    title="MILO API",
    description="The backend for MILO - Autonomous Personal Assistant",
    version="0.1.0",
    lifespan=lifespan
)

frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
async def get_index():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return {"message": "Frontend not ready"}

class ChatRequest(BaseModel):
    prompt: str

class ChatResponse(BaseModel):
    response: str
    execution_log: list

class EnqueueRequest(BaseModel):
    task_name: str
    prompt: str

class EnqueueResponse(BaseModel):
    task_id: int
    status: str

@app.get("/health")
def health_check():
    """Health check endpoint to verify the server is running."""
    return {"status": "ok", "app": "MILO API"}

@app.post("/chat", status_code=200)
def chat_endpoint(request: ChatRequest):
    """
    Endpoint to send prompts to MILO, triggering tool use and returning the response.
    If LLM quotas are exhausted, automatically enqueues the prompt for deferred execution.
    """
    from src.services.db_service import enqueue_task
    try:
        result = generate_response(request.prompt)
        return ChatResponse(
            response=result["response"],
            execution_log=result["execution_log"]
        )
    except Exception as e:
        error_msg = str(e).lower()
        # If both Gemini and Claude fail due to quota/credentials, enqueue the task
        is_quota_issue = any(kw in error_msg for kw in ["quota", "limit", "429", "exhausted", "api_key", "credentials"])
        
        if is_quota_issue:
            try:
                task_id = enqueue_task(
                    task_name="chat_fallback_quota",
                    payload={"prompt": request.prompt}
                )
                return {
                    "response": (
                        f"Lo siento, en este momento el servicio está degradado debido a que se han agotado "
                        f"las cuotas de las APIs (Gemini/Claude). He encolado tu consulta de forma autónoma "
                        f"(Tarea #{task_id}). Se ejecutará en segundo plano en cuanto se restablezcan las cuotas."
                    ),
                    "execution_log": [],
                    "task_id": task_id,
                    "status": "degraded_enqueued"
                }
            except Exception as db_err:
                raise HTTPException(status_code=500, detail=f"Database error during enqueue: {db_err}")
        else:
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


@app.post("/tasks", response_model=EnqueueResponse)
def enqueue_task_endpoint(request: EnqueueRequest):
    """Enqueue a new task for background execution."""
    from src.services.db_service import enqueue_task
    try:
        task_id = enqueue_task(
            task_name=request.task_name,
            payload={"prompt": request.prompt}
        )
        return EnqueueResponse(task_id=task_id, status="enqueued")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enqueue task: {e}")

@app.get("/tasks/{task_id}")
def get_task_status_endpoint(task_id: int):
    """Retrieve the status and results of a specific task."""
    from src.services.db_service import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM task_queue WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Task not found.")
        
    import json
    return {
        "task_id": row["id"],
        "task_name": row["task_name"],
        "payload": json.loads(row["payload"]),
        "status": row["status"],
        "attempts": row["attempts"],
        "created_at": row["created_at"],
        "last_attempt": row["last_attempt"],
        "error": row["error"]
    }

@app.post("/chat/audio", response_model=ChatResponse)
async def chat_audio_endpoint(file: UploadFile = File(...)):
    """
    Endpoint that accepts an audio file (e.g., WAV), transcribes and processes it with Gemini,
    runs tool calls, and returns the response.
    """
    from src.services.gemini_service import generate_audio_response
    try:
        audio_bytes = await file.read()
        mime_type = file.content_type or "audio/wav"
        
        result = generate_audio_response(audio_bytes, mime_type=mime_type)
        
        return ChatResponse(
            response=result["response"],
            execution_log=result["execution_log"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing audio chat: {str(e)}")

@app.get("/session/greeting")
async def session_greeting():
    """
    Endpoint proactivo: genera un saludo de apertura de sesión con señales
    del entorno (errores, tareas pendientes, archivos modificados).
    """
    from src.services.proactive_engine import get_session_greeting
    try:
        result = get_session_greeting()
        return result
    except Exception as e:
        return {"greeting": f"¡Hola! No pude analizar el estado del sistema: {str(e)}", "signals": [], "triggers": []}

@app.post("/skills/check")
async def check_skill_creation(task_type: str = "", metadata: dict = None):
    """
    Endpoint para registrar un patrón de tarea y auto-crear una skill si se detecta
    que la tarea se ha repetido suficientes veces.
    """
    from src.services.skill_creator import auto_create_skill_if_needed, init_skill_tables
    try:
        init_skill_tables()
        result = auto_create_skill_if_needed(task_type, metadata)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking skill creation: {str(e)}")

@app.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket):
    from starlette.concurrency import run_in_threadpool
    from src.services.gemini_service import generate_response, generate_audio_response
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive()
            
            response_text = ""
            if "text" in message:
                user_text = message["text"]
                result = await run_in_threadpool(generate_response, user_text)
                response_text = result["response"]
            elif "bytes" in message:
                audio_bytes = message["bytes"]
                result = await run_in_threadpool(generate_audio_response, audio_bytes, mime_type="audio/webm")
                response_text = result["response"]
            else:
                continue
            
            try:
                # Fallback TTS with gTTS
                tts = gTTS(text=response_text, lang='es')
                fp = io.BytesIO()
                tts.write_to_fp(fp)
                fp.seek(0)
                audio_response_bytes = fp.read()
                
                # Send text and audio
                await websocket.send_json({"type": "text", "text": response_text})
                await websocket.send_bytes(audio_response_bytes)
            except Exception as tts_err:
                print(f"TTS Error: {tts_err}")
                await websocket.send_json({"type": "text", "text": response_text})
                await websocket.send_json({"type": "error", "error": "Error generating audio."})
                
    except WebSocketDisconnect:
        print("WebSocket client disconnected")
    except Exception as e:
        print(f"WebSocket Error: {e}")
        try:
            await websocket.send_json({"type": "error", "error": str(e)})
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    # When running directly, we use src.main:app to support hot reloading from the project root
    uvicorn.run("src.main:app", host=HOST, port=PORT, reload=True)
