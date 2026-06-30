from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_health_check():
    """Verify that the health check endpoint returns 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app": "MILO API"}

def test_chat_audio_endpoint(monkeypatch):
    """Verify that the /chat/audio endpoint accepts file uploads and returns the response."""
    # Mock generate_audio_response inside main
    def mock_generate_audio_response(audio_bytes, mime_type):
        assert audio_bytes == b"mock_audio_bytes"
        assert mime_type == "audio/wav"
        return {
            "response": "Escuché tu comando de voz.",
            "execution_log": [{"tool": "dummy", "args": {}}],
            "provider": "gemini"
        }
        
    monkeypatch.setattr("src.services.gemini_service.generate_audio_response", mock_generate_audio_response)
    
    # Send mock audio file
    files = {"file": ("test.wav", b"mock_audio_bytes", "audio/wav")}
    response = client.post("/chat/audio", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Escuché tu comando de voz."
    assert len(data["execution_log"]) == 1
    assert data["execution_log"][0]["tool"] == "dummy"

