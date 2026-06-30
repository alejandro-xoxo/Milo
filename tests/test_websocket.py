import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from src.main import app

client = TestClient(app)

@patch('src.main.generate_response')
@patch('src.main.gTTS')
def test_websocket_voice_endpoint_text(mock_gtts, mock_generate_response):
    # Mock Gemini response
    mock_generate_response.return_value = {"response": "Hola soy MILO", "execution_log": []}
    
    # Mock gTTS
    mock_tts_instance = MagicMock()
    mock_tts_instance.write_to_fp.side_effect = lambda fp: fp.write(b"fake audio data")
    mock_gtts.return_value = mock_tts_instance
    
    with client.websocket_connect("/ws/voice") as websocket:
        websocket.send_json({"text": "Hola"})
        
        # Wait for JSON response
        data = websocket.receive_json()
        assert data["type"] == "text"
        assert data["text"] == "Hola soy MILO"
        
        # Wait for audio bytes
        audio_bytes = websocket.receive_bytes()
        assert b"fake audio data" in audio_bytes

@patch('src.main.generate_audio_response')
@patch('src.main.gTTS')
def test_websocket_voice_endpoint_audio(mock_gtts, mock_generate_audio_response):
    # Mock Gemini audio response
    mock_generate_audio_response.return_value = {"response": "Recibí tu audio", "execution_log": []}
    
    # Mock gTTS
    mock_tts_instance = MagicMock()
    mock_tts_instance.write_to_fp.side_effect = lambda fp: fp.write(b"fake response audio")
    mock_gtts.return_value = mock_tts_instance
    
    with client.websocket_connect("/ws/voice") as websocket:
        websocket.send_bytes(b"dummy audio content")
        
        data = websocket.receive_json()
        assert data["type"] == "text"
        assert data["text"] == "Recibí tu audio"
        
        audio_bytes = websocket.receive_bytes()
        assert b"fake response audio" in audio_bytes
