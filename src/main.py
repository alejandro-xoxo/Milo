from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
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


if __name__ == "__main__":
    import uvicorn
    # When running directly, we use src.main:app to support hot reloading from the project root
    uvicorn.run("src.main:app", host=HOST, port=PORT, reload=True)
