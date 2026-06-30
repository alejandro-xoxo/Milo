import pytest
from unittest.mock import patch, MagicMock
import subprocess
from src.tools.antigravity import run_antigravity

@patch("src.tools.antigravity.subprocess.run")
def test_run_antigravity_success_research(mock_run):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Task completed successfully"
    mock_run.return_value = mock_result
    
    result = run_antigravity("analyze the code", "research", "/tmp/project")
    
    mock_run.assert_called_once_with(
        ["agy", "run", "analyze the code", "--cwd", "/tmp/project", "--permission", "proceed-in-sandbox"],
        capture_output=True,
        text=True,
        timeout=600
    )
    assert "Antigravity Execution Successful." in result
    assert "Task completed successfully" in result

@patch("src.tools.antigravity.subprocess.run")
def test_run_antigravity_success_code(mock_run):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Code changed successfully"
    mock_run.return_value = mock_result
    
    result = run_antigravity("fix the bug", "code", "/tmp/project")
    
    mock_run.assert_called_once_with(
        ["agy", "run", "fix the bug", "--cwd", "/tmp/project", "--permission", "always-proceed"],
        capture_output=True,
        text=True,
        timeout=600
    )
    assert "Antigravity Execution Successful." in result
    assert "Code changed successfully" in result

@patch("src.tools.antigravity.subprocess.run")
def test_run_antigravity_failure(mock_run):
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = "Some output"
    mock_result.stderr = "Some error"
    mock_run.return_value = mock_result
    
    result = run_antigravity("do something", "code", "/tmp/project")
    
    assert "Antigravity Execution Failed (exit code 1)." in result
    assert "Some output" in result
    assert "Some error" in result

@patch("src.tools.antigravity.subprocess.run")
def test_run_antigravity_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="agy", timeout=600)
    
    result = run_antigravity("do something long", "code", "/tmp/project")
    
    assert "Antigravity Execution Failed: Task timed out after 600 seconds." in result

@patch("src.tools.antigravity.subprocess.run")
def test_run_antigravity_exception(mock_run):
    mock_run.side_effect = Exception("Unexpected error")
    
    result = run_antigravity("do something", "code", "/tmp/project")
    
    assert "Antigravity Execution Failed with exception: Unexpected error" in result
