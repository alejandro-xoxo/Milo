import sqlite3
import os
import json
from datetime import datetime

from src.services.db_service import get_db_connection


def init_skill_tables():
    """Create the task_patterns table for tracking repeated task executions."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS task_patterns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_type TEXT NOT NULL,
        metadata TEXT,
        recorded_at TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def record_task_pattern(task_type: str, metadata: dict = None) -> int:
    """Record a task execution pattern in the database.

    Args:
        task_type: Identifier for the type of task (e.g. 'format_code', 'deploy_service').
        metadata: Optional dictionary with additional context about the execution.

    Returns:
        The row ID of the inserted record.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO task_patterns (task_type, metadata, recorded_at) VALUES (?, ?, ?)",
        (
            task_type,
            json.dumps(metadata) if metadata else None,
            datetime.now().isoformat()
        )
    )
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def detect_repeated_patterns(threshold: int = 3) -> list:
    """Detect task types that have been executed at least `threshold` times.

    Args:
        threshold: Minimum number of occurrences to consider a pattern repeated.

    Returns:
        A list of dicts with 'task_type' and 'count' for each repeated pattern.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT task_type, COUNT(*) as count FROM task_patterns "
        "GROUP BY task_type HAVING count >= ? ORDER BY count DESC",
        (threshold,)
    )
    rows = cursor.fetchall()
    conn.close()

    return [{"task_type": row["task_type"], "count": row["count"]} for row in rows]


def generate_skill_draft(task_type: str, examples: list) -> str:
    """Generate a SKILL.md draft as a string from a task type and its recorded examples.

    This function creates a Markdown document with YAML frontmatter following the
    Antigravity skill format. It does NOT call any external APIs.

    Args:
        task_type: The task type identifier used to derive the skill name.
        examples: A list of metadata dicts from recorded executions.

    Returns:
        A string containing the full SKILL.md content.
    """
    skill_name = task_type.replace("_", " ").title()
    description = f"Skill auto-generada para la tarea repetida: {task_type}"

    # Build examples section from metadata
    examples_section = ""
    for i, example in enumerate(examples, 1):
        if example:
            formatted = json.dumps(example, indent=2, ensure_ascii=False)
            examples_section += f"\n### Ejemplo {i}\n```json\n{formatted}\n```\n"
        else:
            examples_section += f"\n### Ejemplo {i}\n_(Sin metadata adicional)_\n"

    content = f"""---
name: "{skill_name}"
description: "{description}"
---

# {skill_name}

## Descripción

Esta skill fue auto-generada por MILO al detectar que la tarea `{task_type}` se ejecutó repetidamente.
Revisa y ajusta las instrucciones según sea necesario.

## Instrucciones

1. Identificar cuándo el usuario solicita una tarea de tipo `{task_type}`.
2. Seguir el patrón establecido en los ejemplos registrados.
3. Adaptar los parámetros según el contexto actual.

## Ejemplos Registrados
{examples_section}
## Notas

- Esta skill fue creada automáticamente el {datetime.now().strftime('%Y-%m-%d %H:%M')}.
- Se recomienda revisar y personalizar las instrucciones antes de su uso en producción.
"""
    return content


def save_skill(skill_name: str, content: str, base_path: str = None) -> str:
    """Save a SKILL.md file to the .agents/skills directory and update the changelog.

    Args:
        skill_name: Name of the skill (used as directory name, should be snake_case).
        content: The full SKILL.md content string.
        base_path: Optional base path override. Defaults to the project root.

    Returns:
        The absolute path to the created SKILL.md file.
    """
    if base_path is None:
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    skill_dir = os.path.join(base_path, ".agents", "skills", skill_name)
    os.makedirs(skill_dir, exist_ok=True)

    skill_path = os.path.join(skill_dir, "SKILL.md")
    with open(skill_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Update skills_changelog.md
    changelog_path = os.path.join(base_path, ".agents", "skills_changelog.md")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    changelog_entry = f"- **{timestamp}** — Skill `{skill_name}` creada automáticamente por MILO.\n"

    # Append to existing changelog or create a new one
    if os.path.exists(changelog_path):
        with open(changelog_path, "a", encoding="utf-8") as f:
            f.write(changelog_entry)
    else:
        with open(changelog_path, "w", encoding="utf-8") as f:
            f.write("# Skills Changelog\n\n")
            f.write("Registro de skills auto-generadas por MILO.\n\n")
            f.write(changelog_entry)

    return skill_path


def auto_create_skill_if_needed(
    task_type: str, metadata: dict = None, base_path: str = None, threshold: int = 3
) -> dict:
    """Orchestrate the full auto-creation flow: record, detect, generate, and save.

    This is the main entry point for the skill auto-creation system. It:
    1. Records the current task execution.
    2. Checks if the task type has reached the repetition threshold.
    3. If so, generates a SKILL.md draft and saves it.

    Args:
        task_type: The task type identifier.
        metadata: Optional metadata dict for this execution.
        base_path: Optional base path for saving skills.
        threshold: Minimum repetitions to trigger skill creation.

    Returns:
        A dict with 'recorded' (bool), 'skill_created' (bool), and optionally
        'skill_path' (str) if a skill was created.
    """
    # Step 1: Record the pattern
    record_task_pattern(task_type, metadata)

    # Step 2: Check if this task type has reached the threshold
    repeated = detect_repeated_patterns(threshold=threshold)
    matched = [p for p in repeated if p["task_type"] == task_type]

    if not matched:
        return {"recorded": True, "skill_created": False}

    # Step 3: Check if skill already exists to avoid duplicates
    if base_path is None:
        effective_base = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
    else:
        effective_base = base_path

    skill_dir = os.path.join(effective_base, ".agents", "skills", task_type)
    if os.path.exists(os.path.join(skill_dir, "SKILL.md")):
        return {"recorded": True, "skill_created": False, "reason": "skill_already_exists"}

    # Step 4: Gather examples from recorded metadata
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT metadata FROM task_patterns WHERE task_type = ? ORDER BY recorded_at DESC LIMIT 5",
        (task_type,)
    )
    rows = cursor.fetchall()
    conn.close()

    examples = [json.loads(row["metadata"]) if row["metadata"] else None for row in rows]

    # Step 5: Generate and save
    content = generate_skill_draft(task_type, examples)
    skill_path = save_skill(task_type, content, base_path=base_path)

    return {"recorded": True, "skill_created": True, "skill_path": skill_path}
