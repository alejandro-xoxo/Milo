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
    cursor.execute("DELETE FROM task_queue")
    cursor.execute("DELETE FROM chat_history")
    conn.commit()
    conn.close()
    yield
    if os.path.exists("test_milo.db"):
        try:
            os.remove("test_milo.db")
        except:
            pass

@patch("subprocess.run")
def test_agy_brain_ask_success(mock_run):
    # Mock subprocess.run for Codex writing to temporal output file
    def mock_run_side_effect(args, **kwargs):
        try:
            o_idx = args.index("-o")
            out_file = args[o_idx + 1]
            with open(out_file, "w") as f:
                f.write("Respuesta de Codex mockeada")
        except (ValueError, IndexError):
            pass
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Codex header"
        return mock_res

    mock_run.side_effect = mock_run_side_effect

    brain = AgyBrain(".")
    response = brain.ask("Hola")

    assert response == "Respuesta de Codex mockeada"
    # triage + completion calls
    assert mock_run.call_count == 2
    
    # Active engine should be logged as Codex
    active = get_tool_failure_status("active_engine")["disabled_until"]
    assert active == "Codex"

@patch("subprocess.run")
def test_agy_brain_ask_fallback_enqueue(mock_run):
    # Force Codex failure (returncode = 1)
    mock_res = MagicMock()
    mock_res.returncode = 1
    mock_res.stderr = "Codex failed"
    mock_run.return_value = mock_res

    brain = AgyBrain(".")
    response = brain.ask("Hola")

    assert "encolada" in response
    # triage check failed and returned "", ask() attempted to run codex, failed, and enqueued
    # Verify no agy CLI calls were made
    for call in mock_run.call_args_list:
        args = call[0][0]
        assert "agy" not in args

@patch("subprocess.run")
def test_agy_brain_ask_vulcan_trigger(mock_run):
    # Mock agy CLI run
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "Respuesta de Vulcan mockeada"
    mock_run.return_value = mock_res

    brain = AgyBrain(".")
    response = brain.ask("vulcan, crea un archivo")

    assert "Respuesta de Vulcan mockeada" in response
    assert mock_run.call_count == 1
    args = mock_run.call_args[0][0]
    assert "agy" in args
    assert "crea un archivo" in args

@patch("subprocess.run")
def test_agy_brain_ask_vulcan_trigger_failure(mock_run):
    # Mock agy CLI run failing
    mock_res = MagicMock()
    mock_res.returncode = 1
    mock_res.stderr = "Vulcan fatal error"
    mock_run.return_value = mock_res

    brain = AgyBrain(".")
    response = brain.ask("vulcan, crea un archivo")

    assert "Error al ejecutar la tarea en Vulcan: Vulcan fatal error" in response
    assert mock_run.call_count == 1

def test_detect_vulcan_trigger():
    brain = AgyBrain(".")
    # Positivos
    assert brain.detect_vulcan_trigger("vulcan, crea un archivo") is True
    assert brain.detect_vulcan_trigger("Usa Vulcan para listar directorios") is True
    assert brain.detect_vulcan_trigger("Llama a vulcan por favor") is True
    assert brain.detect_vulcan_trigger("activa vulcan ahora") is True
    # Negativos / Falsos positivos
    assert brain.detect_vulcan_trigger("Hola, cómo estás?") is False
    assert brain.detect_vulcan_trigger("No quiero usar vulcan ahora") is False
    assert brain.detect_vulcan_trigger("no uses vulcan para esta tarea") is False
    assert brain.detect_vulcan_trigger("evita vulcan") is False

def test_strip_trigger_phrase():
    brain = AgyBrain(".")
    assert brain.strip_trigger_phrase("vulcan, crea un archivo") == "crea un archivo"
    assert brain.strip_trigger_phrase("Usa Vulcan para listar directorios") == "para listar directorios"
    assert brain.strip_trigger_phrase("Llama a vulcan por favor") == "por favor"
    assert brain.strip_trigger_phrase("activa vulcan ahora") == "ahora"

