import os
import json
import pytest

# Force test database path before importing modules
os.environ["DB_PATH"] = "test_skills.db"

from src.services.db_service import init_db
from src.services.skill_creator import (
    init_skill_tables,
    record_task_pattern,
    detect_repeated_patterns,
    generate_skill_draft,
    save_skill,
    auto_create_skill_if_needed,
)
from src.services.db_service import get_db_connection


@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    """Fixture to initialize test database with skill tables and clean up after tests."""
    init_db()
    init_skill_tables()
    yield
    if os.path.exists("test_skills.db"):
        os.remove("test_skills.db")


# --- Tests for init_skill_tables ---

def test_init_skill_tables_creates_table():
    """Verify that the task_patterns table is correctly created."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row["name"] for row in cursor.fetchall()]
    conn.close()

    assert "task_patterns" in tables


# --- Tests for record_task_pattern ---

def test_record_task_pattern_basic():
    """Verify that a task pattern is recorded and returns a valid row ID."""
    row_id = record_task_pattern("format_code")
    assert row_id > 0

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM task_patterns WHERE id = ?", (row_id,))
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row["task_type"] == "format_code"
    assert row["metadata"] is None
    assert row["recorded_at"] is not None


def test_record_task_pattern_with_metadata():
    """Verify that metadata is stored correctly as JSON."""
    meta = {"language": "python", "file": "main.py"}
    row_id = record_task_pattern("lint_file", metadata=meta)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT metadata FROM task_patterns WHERE id = ?", (row_id,))
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    parsed = json.loads(row["metadata"])
    assert parsed["language"] == "python"
    assert parsed["file"] == "main.py"


# --- Tests for detect_repeated_patterns ---

def test_detect_repeated_patterns_below_threshold():
    """Verify that patterns below the threshold are not returned."""
    record_task_pattern("rare_task")
    record_task_pattern("rare_task")

    result = detect_repeated_patterns(threshold=3)
    task_types = [r["task_type"] for r in result]
    assert "rare_task" not in task_types


def test_detect_repeated_patterns_at_threshold():
    """Verify that patterns at exactly the threshold are returned."""
    for _ in range(3):
        record_task_pattern("common_task")

    result = detect_repeated_patterns(threshold=3)
    task_types = [r["task_type"] for r in result]
    assert "common_task" in task_types

    matched = [r for r in result if r["task_type"] == "common_task"]
    assert matched[0]["count"] == 3


def test_detect_repeated_patterns_above_threshold():
    """Verify that patterns above the threshold are returned with correct count."""
    for _ in range(5):
        record_task_pattern("very_common_task")

    result = detect_repeated_patterns(threshold=3)
    matched = [r for r in result if r["task_type"] == "very_common_task"]
    assert len(matched) == 1
    assert matched[0]["count"] == 5


def test_detect_repeated_patterns_multiple_types():
    """Verify detection works with multiple task types simultaneously."""
    for _ in range(4):
        record_task_pattern("task_a")
    for _ in range(2):
        record_task_pattern("task_b")
    for _ in range(3):
        record_task_pattern("task_c")

    result = detect_repeated_patterns(threshold=3)
    task_types = [r["task_type"] for r in result]

    assert "task_a" in task_types
    assert "task_b" not in task_types
    assert "task_c" in task_types


# --- Tests for generate_skill_draft ---

def test_generate_skill_draft_structure():
    """Verify that the generated draft has YAML frontmatter and expected sections."""
    examples = [{"file": "app.py"}, None, {"file": "utils.py"}]
    content = generate_skill_draft("deploy_service", examples)

    # Check YAML frontmatter
    assert content.startswith("---")
    assert 'name: "Deploy Service"' in content
    assert 'description:' in content

    # Check Markdown sections
    assert "# Deploy Service" in content
    assert "## Descripción" in content
    assert "## Instrucciones" in content
    assert "## Ejemplos Registrados" in content
    assert "## Notas" in content

    # Check examples content
    assert "app.py" in content
    assert "utils.py" in content
    assert "Sin metadata adicional" in content


def test_generate_skill_draft_empty_examples():
    """Verify that the draft handles an empty examples list gracefully."""
    content = generate_skill_draft("empty_task", [])

    assert content.startswith("---")
    assert 'name: "Empty Task"' in content
    assert "## Ejemplos Registrados" in content


def test_generate_skill_draft_task_type_in_content():
    """Verify that the task_type appears in the generated instructions."""
    content = generate_skill_draft("run_tests", [{"suite": "unit"}])
    assert "`run_tests`" in content


# --- Tests for save_skill ---

def test_save_skill_creates_files(tmp_path):
    """Verify that save_skill creates the SKILL.md and changelog files."""
    content = "---\nname: test\n---\n# Test Skill\n"
    skill_path = save_skill("test_skill", content, base_path=str(tmp_path))

    assert os.path.exists(skill_path)
    assert skill_path.endswith("SKILL.md")

    # Verify content was written
    with open(skill_path, "r", encoding="utf-8") as f:
        saved = f.read()
    assert saved == content

    # Verify changelog was created
    changelog_path = os.path.join(str(tmp_path), ".agents", "skills_changelog.md")
    assert os.path.exists(changelog_path)
    with open(changelog_path, "r", encoding="utf-8") as f:
        changelog = f.read()
    assert "test_skill" in changelog
    assert "Skills Changelog" in changelog


def test_save_skill_appends_to_changelog(tmp_path):
    """Verify that saving multiple skills appends entries to the changelog."""
    save_skill("skill_one", "# Skill One", base_path=str(tmp_path))
    save_skill("skill_two", "# Skill Two", base_path=str(tmp_path))

    changelog_path = os.path.join(str(tmp_path), ".agents", "skills_changelog.md")
    with open(changelog_path, "r", encoding="utf-8") as f:
        changelog = f.read()

    assert "skill_one" in changelog
    assert "skill_two" in changelog


def test_save_skill_directory_structure(tmp_path):
    """Verify the correct directory structure: .agents/skills/{name}/SKILL.md."""
    save_skill("my_skill", "# Content", base_path=str(tmp_path))

    expected_dir = os.path.join(str(tmp_path), ".agents", "skills", "my_skill")
    assert os.path.isdir(expected_dir)

    expected_file = os.path.join(expected_dir, "SKILL.md")
    assert os.path.isfile(expected_file)


# --- Tests for auto_create_skill_if_needed ---

def test_auto_create_below_threshold(tmp_path):
    """Verify that no skill is created when below the threshold."""
    result = auto_create_skill_if_needed(
        "infrequent_task", metadata={"key": "val"}, base_path=str(tmp_path)
    )
    assert result["recorded"] is True
    assert result["skill_created"] is False


def test_auto_create_at_threshold(tmp_path):
    """Verify that a skill is created when the threshold is reached."""
    # Record 2 patterns first (below threshold of 3)
    record_task_pattern("auto_task", {"run": 1})
    record_task_pattern("auto_task", {"run": 2})

    # The 3rd call via auto_create should trigger creation
    result = auto_create_skill_if_needed(
        "auto_task", metadata={"run": 3}, base_path=str(tmp_path), threshold=3
    )

    assert result["recorded"] is True
    assert result["skill_created"] is True
    assert "skill_path" in result
    assert os.path.exists(result["skill_path"])

    # Verify SKILL.md content
    with open(result["skill_path"], "r", encoding="utf-8") as f:
        content = f.read()
    assert "auto_task" in content
    assert "Auto Task" in content


def test_auto_create_does_not_duplicate(tmp_path):
    """Verify that auto_create does not overwrite an existing skill."""
    # Trigger creation
    for _ in range(2):
        record_task_pattern("dup_task")
    result1 = auto_create_skill_if_needed(
        "dup_task", base_path=str(tmp_path), threshold=3
    )
    assert result1["skill_created"] is True

    # Record more and try again — should NOT recreate
    result2 = auto_create_skill_if_needed(
        "dup_task", base_path=str(tmp_path), threshold=3
    )
    assert result2["recorded"] is True
    assert result2["skill_created"] is False
    assert result2.get("reason") == "skill_already_exists"


def test_auto_create_records_even_below_threshold(tmp_path):
    """Verify that the pattern is always recorded regardless of skill creation."""
    result = auto_create_skill_if_needed(
        "new_task", metadata={"first": True}, base_path=str(tmp_path), threshold=5
    )
    assert result["recorded"] is True

    # Verify it was stored in the DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) as cnt FROM task_patterns WHERE task_type = ?", ("new_task",)
    )
    row = cursor.fetchone()
    conn.close()
    assert row["cnt"] == 1
