import logging
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential

from src.services.db_service import (
    get_tool_failure_status,
    record_tool_failure,
    reset_tool_failures,
    log_incident
)

logger = logging.getLogger(__name__)

class ToolDisabledException(Exception):
    """Exception raised when a tool is disabled by the circuit breaker."""
    pass

def check_circuit_breaker(tool_name: str):
    """Check if the tool is disabled by the circuit breaker."""
    status = get_tool_failure_status(tool_name)
    disabled_until = status["disabled_until"]
    
    if disabled_until:
        disabled_dt = datetime.fromisoformat(disabled_until)
        if datetime.now() < disabled_dt:
            remaining = (disabled_dt - datetime.now()).total_seconds()
            raise ToolDisabledException(
                f"Tool '{tool_name}' is temporarily disabled due to multiple consecutive failures. "
                f"Try again in {int(remaining)} seconds."
            )
        else:
            # Cooldown period has passed, reset the tool status
            reset_tool_failures(tool_name)

def execute_tool_with_resilience(tool_name: str, tool_func, **kwargs) -> str:
    """
    Executes a tool function with a circuit breaker check and exponential backoff retry layer.
    """
    # 1. Check Circuit Breaker
    try:
        check_circuit_breaker(tool_name)
    except ToolDisabledException as tde:
        logger.warning(f"Execution blocked by Circuit Breaker: {tde}")
        return str(tde)
    
    # 2. Define the retry-decorated function
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True
    )
    def run_with_retry():
        logger.info(f"Running tool '{tool_name}' (kwargs={kwargs})...")
        return tool_func(**kwargs)
        
    try:
        # Run tool
        result = run_with_retry()
        # On success, reset failures
        reset_tool_failures(tool_name)
        return str(result)
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Tool '{tool_name}' failed after retries: {error_msg}")
        
        # Log incident in the SQLite database
        log_incident(tool_name, error_msg, kwargs)
        
        # Record failure in circuit breaker
        record_tool_failure(tool_name)
        
        return f"Error executing tool '{tool_name}': {error_msg}"
