import pytest
from src.services.response_formatter import humanize_response
from unittest.mock import patch, MagicMock

def test_humanize_response_empty():
    res = humanize_response("")
    assert res["subtitle"] == ""
    assert res["speech"] == ""

def test_humanize_response_removes_metadata():
    raw = "Thought: Here is my thinking\nResponse: Hola, soy MILO."
    res = humanize_response(raw)
    assert "Thought:" not in res["subtitle"]
    assert "Response:" not in res["subtitle"]
    assert "Hola, soy MILO." in res["subtitle"]

def test_humanize_response_removes_markdown_for_speech():
    raw = "Aquí tienes un **texto en negrita** y un [enlace](https://google.com)."
    res = humanize_response(raw)
    
    # Subtitle keeps the markdown
    assert "**texto en negrita**" in res["subtitle"]
    
    # Speech removes asterisks and URLs
    assert "*" not in res["speech"]
    assert "texto en negrita" in res["speech"]
    assert "un enlace" in res["speech"]
    assert "https://google.com" not in res["speech"]

@patch('src.services.response_formatter.AgyBrain')
def test_humanize_response_long_text(mock_agy_brain_class):
    # Setup mock
    mock_brain = MagicMock()
    mock_brain.ask.return_value = "Resumen corto."
    mock_agy_brain_class.return_value = mock_brain
    
    # Text > 400 chars
    long_text = "Hola " * 100
    res = humanize_response(long_text)
    
    assert res["subtitle"] == "Resumen corto."
    assert res["speech"] == "Resumen corto."
    mock_brain.ask.assert_called_once()
