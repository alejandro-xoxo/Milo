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

@patch("requests.post")
def test_agy_brain_ask_success(mock_post):
    # Setup mock for OpenClaw gateway (primary engine)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Respuesta de OpenClaw"
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    brain = AgyBrain(".")
    response = brain.ask("Hola")

    assert response == "Respuesta de OpenClaw"
    mock_post.assert_called_once()
    
    # Active engine should be logged as openclaw
    active = get_tool_failure_status("active_engine")["disabled_until"]
    assert active == "openclaw"

@patch("subprocess.run")
@patch("requests.post")
def test_agy_brain_ask_fallback_to_vulcan(mock_post, mock_run):
    # Mock OpenClaw failing (e.g. gateway down, raising ConnectionError)
    mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

    # Setup mock for Vulcan (agy CLI) succeeding
    mock_run_res = MagicMock()
    mock_run_res.returncode = 0
    mock_run_res.stdout = "Respuesta de Vulcan"
    mock_run.return_value = mock_run_res

    brain = AgyBrain(".")
    response = brain.ask("Hola")

    assert response == "Respuesta de Vulcan"
    mock_post.assert_called_once()
    mock_run.assert_called_once()

    # Verify failure recorded for openclaw
    openclaw_status = get_tool_failure_status("openclaw")
    assert openclaw_status["failure_count"] == 1

    # Active engine should be logged as vulcan
    active = get_tool_failure_status("active_engine")["disabled_until"]
    assert active == "vulcan"

@patch("subprocess.run")
@patch("requests.post")
def test_agy_brain_ask_circuit_breaker(mock_post, mock_run):
    # Force disable 'openclaw' in circuit breaker (5 failures)
    from src.services.db_service import record_tool_failure
    for _ in range(5):
        record_tool_failure("openclaw", threshold=5)

    # Setup mock for Vulcan succeeding
    mock_run_res = MagicMock()
    mock_run_res.returncode = 0
    mock_run_res.stdout = "Respuesta de Vulcan"
    mock_run.return_value = mock_run_res

    brain = AgyBrain(".")
    response = brain.ask("Hola")

    assert response == "Respuesta de Vulcan"
    
    # OpenClaw HTTP post should NOT be called because of active circuit breaker
    mock_post.assert_not_called()
    mock_run.assert_called_once()

    # Active engine should be logged as vulcan
    active = get_tool_failure_status("active_engine")["disabled_until"]
    assert active == "vulcan"
