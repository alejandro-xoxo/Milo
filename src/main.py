from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src.services.gemini_service import generate_response
from src.config import HOST, PORT

app = FastAPI(
    title="MILO API",
    description="The backend for MILO - Autonomous Personal Assistant",
    version="0.1.0"
)

class ChatRequest(BaseModel):
    prompt: str

class ChatResponse(BaseModel):
    response: str
    execution_log: list

@app.get("/health")
def health_check():
    """Health check endpoint to verify the server is running."""
    return {"status": "ok", "app": "MILO API"}

@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """
    Endpoint to send prompts to MILO, triggering tool use and returning the response.
    """
    try:
        result = generate_response(request.prompt)
        return ChatResponse(
            response=result["response"],
            execution_log=result["execution_log"]
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    # When running directly, we use src.main:app to support hot reloading from the project root
    uvicorn.run("src.main:app", host=HOST, port=PORT, reload=True)
