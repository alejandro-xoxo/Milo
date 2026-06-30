import os
import pytest
import subprocess
import requests
from unittest.mock import patch, MagicMock
from src.services.db_service import init_db, get_db_connection, get_tool_failure_status
from src.services.agy_brain import AgyBrain
from src.services.circuit_breaker import ToolDisabledException

# Force test database path
os.environ["DB_PATH"] = "test_milo.db"

@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    """Fixture to initialize a test database and clean it up after tests."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tool_status")
    cursor.execute("DELETE FROM incidents")
    conn.commit()
    conn.close()
    yield
    if os.path.exists("test_milo.db"):
        os.remove("test_milo.db")

@patch("subprocess.run")
def test_agy_brain_ask_success(mock_run):
    # Setup mock for subprocess.run
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Respuesta de Agy"
    mock_run.return_value = mock_result

    brain = AgyBrain(".")
    response = brain.ask("Hola")

    assert response == "Respuesta de Agy"
    mock_run.assert_called_once()
    
    # Active engine should be agy
    active = get_tool_failure_status("active_engine")["disabled_until"]
    assert active == "agy"

@patch("subprocess.run")
@patch("requests.post")
def test_agy_brain_ask_fallback_on_429(mock_post, mock_run):
    # Setup mock for agy failing (429 Quota issue)
    mock_run_res = MagicMock()
    mock_run_res.returncode = 1
    mock_run_res.stderr = "RESOURCE_EXHAUSTED: API quota exhausted (429)"
    mock_run.return_value = mock_run_res

    # Setup mock for OpenClaw gateway
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Respuesta desde OpenClaw fallback"
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    brain = AgyBrain(".")
    response = brain.ask("Hola")

    assert response == "Respuesta desde OpenClaw fallback"
    mock_run.assert_called_once()
    mock_post.assert_called_once()

    # Verify failure recorded for agy
    agy_status = get_tool_failure_status("agy")
    assert agy_status["failure_count"] == 1

    # Active engine should be logged as openclaw
    active = get_tool_failure_status("active_engine")["disabled_until"]
    assert active == "openclaw"

@patch("subprocess.run")
@patch("requests.post")
def test_agy_brain_ask_circuit_breaker(mock_post, mock_run):
    # Setup mock for OpenClaw gateway
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Respuesta de OpenClaw directo"
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    # Force disable 'agy' in circuit breaker (5 failures)
    from src.services.db_service import record_tool_failure
    for _ in range(5):
        record_tool_failure("agy", threshold=5)

    brain = AgyBrain(".")
    response = brain.ask("Hola")

    assert response == "Respuesta de OpenClaw directo"
    
    # Subprocess.run should NOT be called because of active circuit breaker
    mock_run.assert_not_called()
    mock_post.assert_called_once()

    # Active engine should be logged as openclaw
    active = get_tool_failure_status("active_engine")["disabled_until"]
    assert active == "openclaw"
