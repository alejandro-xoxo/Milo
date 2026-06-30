"""
Tests unitarios para el Motor de Proactividad de MILO.

Cubren:
    - gather_signals() con base de datos vacía y con datos.
    - evaluate_triggers() con distintas combinaciones de señales.
    - generate_proactive_message() con y sin triggers.
    - get_session_greeting() como orquestador completo.
"""

import os
import json
import pytest
from datetime import datetime, timedelta

# Forzar ruta de base de datos de prueba ANTES de importar cualquier servicio
os.environ["DB_PATH"] = "test_proactive.db"
# Apuntar PROJECT_ROOT a un directorio temporal para evitar lecturas reales
os.environ["PROJECT_ROOT"] = "/tmp/milo_proactive_test"

from src.services.db_service import (
    init_db,
    get_db_connection,
    log_incident,
    resolve_incident,
    enqueue_task,
)
from src.services.proactive_engine import (
    gather_signals,
    evaluate_triggers,
    generate_proactive_message,
    get_session_greeting,
    ERROR_ALERT_THRESHOLD,
    TASK_STALE_HOURS,
)


@pytest.fixture(autouse=True)
def setup_and_teardown_db(tmp_path):
    """Fixture que inicializa la BD de prueba y la limpia al finalizar."""
    # Crear directorio temporal simulando src/ con un archivo .py reciente
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "dummy_module.py").write_text("# dummy")
    os.environ["PROJECT_ROOT"] = str(tmp_path)

    init_db()
    yield
    # Cleanup
    if os.path.exists("test_proactive.db"):
        os.remove("test_proactive.db")


# ---------------------------------------------------------------------------
# Tests de gather_signals
# ---------------------------------------------------------------------------

class TestGatherSignals:
    """Verifica la recopilación de señales desde la BD y el sistema de archivos."""

    def test_empty_database_returns_empty_signals(self):
        """Sin datos, las listas de errores y tareas deben estar vacías."""
        signals = gather_signals()
        assert signals["unresolved_errors"] == []
        assert signals["pending_tasks"] == []
        # recent_files puede tener el dummy_module.py del fixture
        assert isinstance(signals["recent_files"], list)

    def test_unresolved_errors_are_detected(self):
        """Los errores no resueltos deben aparecer en las señales."""
        log_incident("tool_a", "Error de conexión")
        log_incident("tool_b", "Timeout")

        signals = gather_signals()
        assert len(signals["unresolved_errors"]) == 2
        tools = {e["tool"] for e in signals["unresolved_errors"]}
        assert "tool_a" in tools
        assert "tool_b" in tools

    def test_resolved_errors_are_excluded(self):
        """Los errores resueltos NO deben aparecer en las señales."""
        incident_id = log_incident("tool_c", "Error temporal")
        resolve_incident(incident_id, "Auto-reparado")

        signals = gather_signals()
        unresolved_ids = {e["id"] for e in signals["unresolved_errors"]}
        assert incident_id not in unresolved_ids

    def test_pending_tasks_are_detected(self):
        """Las tareas pendientes deben aparecer en las señales."""
        enqueue_task("backup", {"target": "/data"})
        enqueue_task("report", {"format": "pdf"})

        signals = gather_signals()
        assert len(signals["pending_tasks"]) == 2

    def test_recent_files_detected_from_scan_dir(self):
        """El archivo dummy creado por el fixture debe detectarse como reciente."""
        signals = gather_signals()
        assert any("dummy_module.py" in f for f in signals["recent_files"])


# ---------------------------------------------------------------------------
# Tests de evaluate_triggers
# ---------------------------------------------------------------------------

class TestEvaluateTriggers:
    """Verifica que las reglas de evaluación de triggers funcionen correctamente."""

    def test_no_triggers_on_empty_signals(self):
        """Sin señales, no debe haber triggers."""
        signals = {
            "unresolved_errors": [],
            "pending_tasks": [],
            "recent_files": [],
        }
        triggers = evaluate_triggers(signals)
        assert triggers == []

    def test_error_alert_above_threshold(self):
        """Más de ERROR_ALERT_THRESHOLD errores dispara trigger de tipo 'error_alert'."""
        errors = [
            {"id": i, "timestamp": datetime.now().isoformat(),
             "tool": f"tool_{i}", "error": f"Error {i}"}
            for i in range(ERROR_ALERT_THRESHOLD + 1)
        ]
        signals = {
            "unresolved_errors": errors,
            "pending_tasks": [],
            "recent_files": [],
        }
        triggers = evaluate_triggers(signals)
        alert_triggers = [t for t in triggers if t["type"] == "error_alert"]
        assert len(alert_triggers) == 1
        assert alert_triggers[0]["severity"] == "high"

    def test_error_notice_below_threshold(self):
        """Menos de ERROR_ALERT_THRESHOLD errores (pero > 0) dispara 'error_notice'."""
        errors = [
            {"id": 1, "timestamp": datetime.now().isoformat(),
             "tool": "tool_x", "error": "Minor error"}
        ]
        signals = {
            "unresolved_errors": errors,
            "pending_tasks": [],
            "recent_files": [],
        }
        triggers = evaluate_triggers(signals)
        notice_triggers = [t for t in triggers if t["type"] == "error_notice"]
        assert len(notice_triggers) == 1
        assert notice_triggers[0]["severity"] == "low"

    def test_stale_tasks_trigger(self):
        """Tareas creadas hace más de TASK_STALE_HOURS horas disparan 'stale_tasks'."""
        old_timestamp = (
            datetime.now() - timedelta(hours=TASK_STALE_HOURS + 1)
        ).isoformat()
        signals = {
            "unresolved_errors": [],
            "pending_tasks": [
                {"id": 1, "task_name": "old_task",
                 "created_at": old_timestamp, "attempts": 0}
            ],
            "recent_files": [],
        }
        triggers = evaluate_triggers(signals)
        stale = [t for t in triggers if t["type"] == "stale_tasks"]
        assert len(stale) == 1
        assert stale[0]["severity"] == "medium"

    def test_recent_tasks_do_not_trigger(self):
        """Tareas recientes NO deben disparar el trigger de tareas envejecidas."""
        recent_timestamp = datetime.now().isoformat()
        signals = {
            "unresolved_errors": [],
            "pending_tasks": [
                {"id": 1, "task_name": "fresh_task",
                 "created_at": recent_timestamp, "attempts": 0}
            ],
            "recent_files": [],
        }
        triggers = evaluate_triggers(signals)
        stale = [t for t in triggers if t["type"] == "stale_tasks"]
        assert len(stale) == 0

    def test_recent_activity_trigger(self):
        """Archivos recientes disparan trigger 'recent_activity'."""
        signals = {
            "unresolved_errors": [],
            "pending_tasks": [],
            "recent_files": ["src/main.py", "src/utils.py"],
        }
        triggers = evaluate_triggers(signals)
        activity = [t for t in triggers if t["type"] == "recent_activity"]
        assert len(activity) == 1
        assert activity[0]["severity"] == "info"

    def test_multiple_triggers_combined(self):
        """Múltiples condiciones activas generan múltiples triggers."""
        old_timestamp = (
            datetime.now() - timedelta(hours=TASK_STALE_HOURS + 5)
        ).isoformat()
        errors = [
            {"id": i, "timestamp": datetime.now().isoformat(),
             "tool": "tool", "error": "err"}
            for i in range(ERROR_ALERT_THRESHOLD + 1)
        ]
        signals = {
            "unresolved_errors": errors,
            "pending_tasks": [
                {"id": 1, "task_name": "stale",
                 "created_at": old_timestamp, "attempts": 0}
            ],
            "recent_files": ["a.py"],
        }
        triggers = evaluate_triggers(signals)
        types = {t["type"] for t in triggers}
        assert "error_alert" in types
        assert "stale_tasks" in types
        assert "recent_activity" in types


# ---------------------------------------------------------------------------
# Tests de generate_proactive_message
# ---------------------------------------------------------------------------

class TestGenerateProactiveMessage:
    """Verifica la generación del mensaje proactivo."""

    def test_no_triggers_produces_all_clear_message(self):
        """Sin triggers, el mensaje debe indicar que todo está en orden."""
        signals = {
            "unresolved_errors": [],
            "pending_tasks": [],
            "recent_files": [],
        }
        message = generate_proactive_message([], signals)
        assert "Todo en orden" in message

    def test_message_contains_trigger_details(self):
        """El mensaje debe incluir los detalles de cada trigger."""
        triggers = [
            {"type": "error_alert", "severity": "high",
             "detail": "Hay 5 errores sin resolver."},
        ]
        signals = {
            "unresolved_errors": [{}] * 5,
            "pending_tasks": [],
            "recent_files": [],
        }
        message = generate_proactive_message(triggers, signals)
        assert "5 errores sin resolver" in message
        assert "🚨" in message

    def test_message_includes_summary_line(self):
        """El mensaje debe incluir la línea de resumen con conteos."""
        triggers = [
            {"type": "error_notice", "severity": "low",
             "detail": "1 error pendiente."},
        ]
        signals = {
            "unresolved_errors": [{}],
            "pending_tasks": [{}] * 3,
            "recent_files": [],
        }
        message = generate_proactive_message(triggers, signals)
        assert "1 error(es)" in message
        assert "3 tarea(s)" in message

    def test_high_severity_shown_first(self):
        """Los triggers de alta severidad deben mostrarse antes que los de baja."""
        triggers = [
            {"type": "recent_activity", "severity": "info",
             "detail": "Archivos recientes."},
            {"type": "error_alert", "severity": "high",
             "detail": "Errores críticos."},
        ]
        signals = {
            "unresolved_errors": [],
            "pending_tasks": [],
            "recent_files": [],
        }
        message = generate_proactive_message(triggers, signals)
        pos_high = message.index("Errores críticos")
        pos_info = message.index("Archivos recientes")
        assert pos_high < pos_info


# ---------------------------------------------------------------------------
# Tests de get_session_greeting (integración)
# ---------------------------------------------------------------------------

class TestGetSessionGreeting:
    """Verifica el flujo orquestado completo."""

    def test_returns_expected_structure(self):
        """El resultado debe tener las claves greeting, signals y triggers."""
        result = get_session_greeting()
        assert "greeting" in result
        assert "signals" in result
        assert "triggers" in result
        assert isinstance(result["greeting"], str)
        assert isinstance(result["signals"], dict)
        assert isinstance(result["triggers"], list)

    def test_greeting_with_no_data_is_all_clear(self):
        """Con BD vacía (sin errores/tareas), el saludo indica que todo está bien."""
        result = get_session_greeting()
        # Puede haber trigger de recent_activity por el dummy file del fixture
        # pero no debe haber error_alert ni stale_tasks
        error_triggers = [
            t for t in result["triggers"] if t["type"] == "error_alert"
        ]
        assert len(error_triggers) == 0

    def test_greeting_with_errors_contains_alert(self):
        """Con suficientes errores, el saludo debe contener alerta."""
        for i in range(ERROR_ALERT_THRESHOLD + 1):
            log_incident(f"tool_{i}", f"Error grave #{i}")

        result = get_session_greeting()
        assert any(t["type"] == "error_alert" for t in result["triggers"])
        assert "error" in result["greeting"].lower()

    def test_greeting_with_stale_tasks(self):
        """Con tareas envejecidas, el saludo debe mencionarlas."""
        conn = get_db_connection()
        cursor = conn.cursor()
        old_time = (
            datetime.now() - timedelta(hours=TASK_STALE_HOURS + 2)
        ).isoformat()
        cursor.execute(
            "INSERT INTO task_queue (task_name, payload, status, created_at) "
            "VALUES (?, ?, 'pending', ?)",
            ("tarea_vieja", json.dumps({"info": "test"}), old_time),
        )
        conn.commit()
        conn.close()

        result = get_session_greeting()
        assert any(t["type"] == "stale_tasks" for t in result["triggers"])
        assert "tarea" in result["greeting"].lower()
