import os
import pytest
from datetime import datetime, timedelta

# Force test database path
os.environ["DB_PATH"] = "test_milo.db"

from src.services.db_service import (
    init_db,
    get_db_connection,
    log_incident,
    get_tool_failure_status,
    record_tool_failure,
    reset_tool_failures,
    enqueue_task,
    get_next_pending_task,
    update_task_status
)
from src.services.circuit_breaker import execute_tool_with_resilience, ToolDisabledException

@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    """Fixture to initialize a test database and clean it up after tests."""
    init_db()
    yield
    # Cleanup test database file
    if os.path.exists("test_milo.db"):
        os.remove("test_milo.db")

def test_db_initialization():
    """Verify that tables are correctly initialized in the test database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row["name"] for row in cursor.fetchall()]
    
    assert "incidents" in tables
    assert "task_queue" in tables
    assert "tool_status" in tables
    conn.close()

def test_log_incident():
    """Verify that incidents are logged correctly in SQLite."""
    incident_id = log_incident("dummy_tool", "DivisionByZeroError", {"param1": 42})
    assert incident_id > 0
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    row = cursor.fetchone()
    conn.close()
    
    assert row is not None
    assert row["tool"] == "dummy_tool"
    assert row["error"] == "DivisionByZeroError"
    assert "param1" in row["args"]

def test_circuit_breaker_failure_accumulation():
    """Verify that multiple failures trigger the circuit breaker."""
    tool_name = "flaky_tool"
    
    # Initial status
    status = get_tool_failure_status(tool_name)
    assert status["failure_count"] == 0
    assert status["disabled_until"] is None
    
    # Record 4 failures (less than threshold of 5)
    for _ in range(4):
        record_tool_failure(tool_name, threshold=5)
        
    status = get_tool_failure_status(tool_name)
    assert status["failure_count"] == 4
    assert status["disabled_until"] is None
    
    # Record 5th failure -> should disable tool
    record_tool_failure(tool_name, threshold=5)
    status = get_tool_failure_status(tool_name)
    assert status["failure_count"] == 5
    assert status["disabled_until"] is not None

def test_circuit_breaker_tool_execution_resilience():
    """Verify execute_tool_with_resilience retries and triggers the circuit breaker."""
    failures = 0
    
    def dummy_failing_function(x):
        nonlocal failures
        failures += 1
        raise ValueError("Simulated network outage")
        
    tool_name = "unstable_endpoint"
    
    # Run failing function (should attempt 3 retries and then return error string)
    result = execute_tool_with_resilience(tool_name, dummy_failing_function, x=10)
    
    # Verify tenacity retried 3 times on the first invocation
    assert failures == 3
    assert "Simulated network outage" in result
    
    # Verify 1 failure was registered in DB
    status = get_tool_failure_status(tool_name)
    assert status["failure_count"] == 1
    
    # Force disable by recording 4 more failures directly
    for _ in range(4):
        record_tool_failure(tool_name)
        
    # Attempting to run it again should raise ToolDisabledException (circuit breaker active)
    result_disabled = execute_tool_with_resilience(tool_name, dummy_failing_function, x=10)
    assert "temporarily disabled" in result_disabled
    
    # The dummy function should NOT have been called again (failures stays at 3)
    assert failures == 3

def test_task_queue_operations():
    """Verify that tasks can be enqueued, fetched, and updated in order."""
    # Enqueue two tasks
    task_id1 = enqueue_task("task1", {"prompt": "First task"})
    task_id2 = enqueue_task("task2", {"prompt": "Second task"})
    
    assert task_id1 > 0
    assert task_id2 > task_id1
    
    # Get first pending task
    task = get_next_pending_task()
    assert task is not None
    assert task["id"] == task_id1
    assert task["task_name"] == "task1"
    assert task["payload"]["prompt"] == "First task"
    
    # Mark first task as running
    update_task_status(task_id1, "running")
    
    # Since task 1 is running, the next pending should be task 2
    next_task = get_next_pending_task()
    assert next_task is not None
    assert next_task["id"] == task_id2
    assert next_task["task_name"] == "task2"
    
    # Complete task 1 and task 2
    update_task_status(task_id1, "completed")
    update_task_status(task_id2, "completed")
    
    # Queue should be empty now
    assert get_next_pending_task() is None

def test_chat_endpoint_degraded_fallback(monkeypatch):
    """Verify that if generate_response raises a quota exception, the chat endpoint enqueues it."""
    from fastapi.testclient import TestClient
    from src.main import app
    from src.services.db_service import get_next_pending_task
    
    client = TestClient(app)
    
    # Mock generate_response to raise a ResourceExhausted exception
    def mock_generate_response(prompt):
        raise RuntimeError("API quota exhausted (429)")
        
    monkeypatch.setattr("src.main.generate_response", mock_generate_response)
    
    response = client.post("/chat", json={"prompt": "Test degraded prompt"})
    assert response.status_code == 200
    data = response.json()
    
    assert "degradado debido a que se han agotado" in data["response"]
    assert data["status"] == "degraded_enqueued"
    assert "task_id" in data
    
    # Check that it was actually enqueued in the test database
    task = get_next_pending_task()
    assert task is not None
    assert task["task_name"] == "chat_fallback_quota"
    assert task["payload"]["prompt"] == "Test degraded prompt"

def test_circuit_breaker_reset_failures():
    """Verify that a successful tool run resets the failure count to 0."""
    from src.services.db_service import record_tool_failure, get_tool_failure_status
    from src.services.circuit_breaker import execute_tool_with_resilience
    
    tool_name = "test_reset_tool"
    
    # Record a failure
    record_tool_failure(tool_name)
    status = get_tool_failure_status(tool_name)
    assert status["failure_count"] == 1
    
    # Run successful function
    def dummy_success(x):
        return x * 2
        
    result = execute_tool_with_resilience(tool_name, dummy_success, x=5)
    assert result == "10"
    
    # Failure count should be reset to 0
    status_after = get_tool_failure_status(tool_name)
    assert status_after["failure_count"] == 0



