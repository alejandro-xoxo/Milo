import subprocess
import logging

logger = logging.getLogger(__name__)

def run_antigravity(task: str, mode: str, project_path: str = "/home/alejandro/Proyectos/Milo") -> str:
    """
    Executes a task using the Antigravity CLI (agy).
    
    Args:
        task: The task description or goal.
        mode: The mode of execution, either 'research' or 'code'.
        project_path: The absolute path to the project.
        
    Returns:
        The output of the Antigravity execution as a string.
    """
    permission = "proceed-in-sandbox" if mode == "research" else "always-proceed"
    
    try:
        logger.info(f"Running Antigravity for task: '{task}' in {mode} mode with permission {permission}")
        result = subprocess.run(
            ["agy", "run", task, "--cwd", project_path, "--permission", permission],
            capture_output=True,
            text=True,
            timeout=600
        )
        if result.returncode == 0:
            return f"Antigravity Execution Successful.\n\nStdout:\n{result.stdout}"
        else:
            return f"Antigravity Execution Failed (exit code {result.returncode}).\n\nStdout:\n{result.stdout}\n\nStderr:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "Antigravity Execution Failed: Task timed out after 600 seconds."
    except Exception as e:
        logger.error(f"Error running Antigravity: {e}")
        return f"Antigravity Execution Failed with exception: {str(e)}"
