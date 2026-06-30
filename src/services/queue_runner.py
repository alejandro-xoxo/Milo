import asyncio
import logging
from src.services.db_service import (
    get_next_pending_task,
    update_task_status,
    increment_task_attempts
)
from src.services.gemini_service import generate_response

logger = logging.getLogger(__name__)

# Global flag to control the background runner task
_running = True
_runner_task = None

async def start_queue_runner():
    """Continuously poll and execute pending tasks from the SQLite queue."""
    global _running
    logger.info("Starting background task queue runner...")
    
    while _running:
        try:
            task = get_next_pending_task()
            if task:
                task_id = task["id"]
                task_name = task["task_name"]
                payload = task["payload"]
                prompt = payload.get("prompt")
                
                logger.info(f"[Queue Runner] Processing task {task_id}: {task_name}")
                update_task_status(task_id, "running")
                increment_task_attempts(task_id)
                
                if not prompt:
                    update_task_status(task_id, "failed", "Error: Payload is missing 'prompt'.")
                    continue
                
                try:
                    # Execute task by calling the LLM chain (which includes Claude fallback)
                    result = generate_response(prompt)
                    logger.info(f"[Queue Runner] Task {task_id} completed successfully via {result.get('provider')}.")
                    update_task_status(task_id, "completed")
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"[Queue Runner] Task {task_id} failed: {error_msg}")
                    # If both APIs failed due to quota/network, set to failed
                    # The user can re-trigger or we can retry later.
                    update_task_status(task_id, "failed", error_msg)
            else:
                # No tasks in queue, sleep for 5 seconds
                await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"[Queue Runner] Error in loop: {e}")
            await asyncio.sleep(10)

def init_runner(loop: asyncio.AbstractEventLoop = None):
    """Launch the queue runner as a background task."""
    global _runner_task, _running
    _running = True
    if loop is None:
        loop = asyncio.get_event_loop()
    _runner_task = loop.create_task(start_queue_runner())

def stop_runner():
    """Gracefully shutdown the queue runner."""
    global _running, _runner_task
    logger.info("Stopping background task queue runner...")
    _running = False
    if _runner_task:
        _runner_task.cancel()
