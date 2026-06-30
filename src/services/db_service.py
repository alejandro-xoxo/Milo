import sqlite3
import os
import json
from datetime import datetime, timedelta

def get_db_path() -> str:
    """Return the database path, allowing dynamic override via environment variables."""
    return os.getenv("DB_PATH", "milo.db")

def get_db_connection():
    """Establish a connection to the SQLite database."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database tables for tasks, incidents, and circuit breakers."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Incidents Table (for self-healing and error logging)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        tool TEXT NOT NULL,
        error TEXT NOT NULL,
        args TEXT,
        resolved INTEGER DEFAULT 0,
        resolution TEXT
    )
    """)
    
    # 2. Task Queue Table (to survive quota exhaustion and schedule actions)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS task_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_name TEXT NOT NULL,
        payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        last_attempt TEXT,
        error TEXT
    )
    """)
    
    # 3. Circuit Breaker Table (to disable failing tools temporarily)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tool_status (
        tool_name TEXT PRIMARY KEY,
        failure_count INTEGER DEFAULT 0,
        disabled_until TEXT
    )
    """)
    
    # 4. Chat History Table (for session persistence and context trimming)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        summary TEXT,
        timestamp TEXT NOT NULL
    )
    """)
    
    conn.commit()
    conn.close()

# --- HELPER FUNCTIONS FOR INCIDENTS ---

def log_incident(tool: str, error: str, args: dict = None) -> int:
    """Log an execution incident in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO incidents (timestamp, tool, error, args) VALUES (?, ?, ?, ?)",
        (
            datetime.now().isoformat(),
            tool,
            error,
            json.dumps(args) if args else None
        )
    )
    incident_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return incident_id

def resolve_incident(incident_id: int, resolution: str):
    """Mark an incident as resolved with a specific resolution details."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE incidents SET resolved = 1, resolution = ? WHERE id = ?",
        (resolution, incident_id)
    )
    conn.commit()
    conn.close()

# --- HELPER FUNCTIONS FOR TOOL STATUS (CIRCUIT BREAKER) ---

def get_tool_failure_status(tool_name: str) -> dict:
    """Get the failure count and disable timestamp of a tool."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT failure_count, disabled_until FROM tool_status WHERE tool_name = ?",
        (tool_name,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {"failure_count": row["failure_count"], "disabled_until": row["disabled_until"]}
    return {"failure_count": 0, "disabled_until": None}

def record_tool_failure(tool_name: str, threshold: int = 5, cooldown_minutes: int = 15):
    """Record a failure for a tool and disable it if threshold is reached."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    status = get_tool_failure_status(tool_name)
    new_failures = status["failure_count"] + 1
    disabled_until = None
    
    if new_failures >= threshold:
        disabled_until = (datetime.now() + timedelta(minutes=cooldown_minutes)).isoformat()
        
    cursor.execute("""
    INSERT INTO tool_status (tool_name, failure_count, disabled_until)
    VALUES (?, ?, ?)
    ON CONFLICT(tool_name) DO UPDATE SET
        failure_count = excluded.failure_count,
        disabled_until = excluded.disabled_until
    """, (tool_name, new_failures, disabled_until))
    
    conn.commit()
    conn.close()

def reset_tool_failures(tool_name: str):
    """Reset the failure count of a tool to zero (successful run)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO tool_status (tool_name, failure_count, disabled_until)
    VALUES (?, 0, NULL)
    ON CONFLICT(tool_name) DO UPDATE SET
        failure_count = 0,
        disabled_until = NULL
    """, (tool_name,))
    conn.commit()
    conn.close()

# --- HELPER FUNCTIONS FOR TASK QUEUE ---

def enqueue_task(task_name: str, payload: dict) -> int:
    """Add a new task to the queue for deferred execution."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO task_queue (task_name, payload, status, created_at) VALUES (?, ?, 'pending', ?)",
        (task_name, json.dumps(payload), datetime.now().isoformat())
    )
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return task_id

def get_next_pending_task() -> dict:
    """Retrieve the oldest pending task from the queue."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM task_queue WHERE status = 'pending' ORDER BY id ASC LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row["id"],
            "task_name": row["task_name"],
            "payload": json.loads(row["payload"]),
            "attempts": row["attempts"],
            "created_at": row["created_at"]
        }
    return None

def update_task_status(task_id: int, status: str, error: str = None):
    """Update the status and optional error message of a task."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE task_queue SET status = ?, error = ?, last_attempt = ? WHERE id = ?",
        (status, error, datetime.now().isoformat(), task_id)
    )
    conn.commit()
    conn.close()

def increment_task_attempts(task_id: int):
    """Increment the attempt counter for a task."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE task_queue SET attempts = attempts + 1 WHERE id = ?",
        (task_id,)
    )
    conn.commit()
    conn.close()

# --- HELPER FUNCTIONS FOR CHAT HISTORY & CONTEXT ---

def add_chat_message(session_id: str, role: str, content: str, summary: str = None) -> int:
    """Insert a chat message into history."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_history (session_id, role, content, summary, timestamp) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, summary, datetime.now().isoformat())
    )
    msg_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return msg_id

def get_chat_history(session_id: str, limit: int = 10) -> list:
    """Retrieve the last N chat messages of a session in chronological order."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, role, content, summary FROM chat_history WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    # Reverse to keep chronological order
    return [{"id": r["id"], "role": r["role"], "content": r["content"], "summary": r["summary"]} for r in reversed(rows)]

def get_last_summary(session_id: str) -> dict:
    """Get the latest cached summary for the session."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, summary FROM chat_history WHERE session_id = ? AND summary IS NOT NULL ORDER BY id DESC LIMIT 1",
        (session_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row["id"], "summary": row["summary"]}
    return {"id": 0, "summary": None}

def update_message_summary(msg_id: int, summary: str):
    """Update the summary column for a specific message."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE chat_history SET summary = ? WHERE id = ?",
        (summary, msg_id)
    )
    conn.commit()
    conn.close()

