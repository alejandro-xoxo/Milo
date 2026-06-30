"""
Motor de Proactividad de MILO.

Este módulo permite que MILO detecte señales del entorno al inicio de cada
sesión (errores recientes no resueltos, tareas pendientes envejecidas, archivos
modificados recientemente) y genere un mensaje de apertura proactivo en español.
"""

import os
import logging
from datetime import datetime, timedelta
from pathlib import Path

from src.services.db_service import get_db_connection

logger = logging.getLogger(__name__)

# --- Umbrales de configuración ---
ERROR_ALERT_THRESHOLD = 3          # Cantidad de errores no resueltos para disparar alerta
TASK_STALE_HOURS = 24              # Horas para considerar una tarea como "envejecida"
RECENT_FILES_HOURS = 24            # Ventana temporal para detectar archivos recientes
RECENT_FILES_SCAN_DIR = "src/"     # Directorio base para escanear archivos modificados


def gather_signals() -> dict:
    """Recopila señales del entorno: errores no resueltos, tareas pendientes,
    archivos modificados recientemente y estado de salud de OpenClaw.

    Returns:
        dict con las señales correspondientes.
    """
    signals = {
        "unresolved_errors": _get_unresolved_errors(),
        "pending_tasks": _get_pending_tasks(),
        "recent_files": _get_recently_modified_files(),
        "openclaw_healthy": _check_openclaw_health(),
    }
    logger.info(
        "Señales recopiladas: %d errores, %d tareas, %d archivos recientes, OpenClaw healthy: %s",
        len(signals["unresolved_errors"]),
        len(signals["pending_tasks"]),
        len(signals["recent_files"]),
        signals["openclaw_healthy"],
    )
    return signals


def evaluate_triggers(signals: dict) -> list[dict]:
    """Evalúa reglas simples sobre las señales y devuelve una lista de triggers
    activados.

    Reglas implementadas:
        - Si hay >= ERROR_ALERT_THRESHOLD errores no resueltos → alerta de errores.
        - Si hay tareas pendientes con más de TASK_STALE_HOURS horas → recordatorio.
        - Si hay archivos modificados recientemente → informe de actividad.
        - Si OpenClaw está caído o inaccesible → advertencia de caída de orquestador.

    Args:
        signals: diccionario devuelto por gather_signals().

    Returns:
        Lista de dicts, cada uno con 'type', 'severity' y 'detail'.
    """
    triggers: list[dict] = []

    # --- Regla 1: Alerta de errores ---
    unresolved = signals.get("unresolved_errors", [])
    if len(unresolved) >= ERROR_ALERT_THRESHOLD:
        tools_affected = list({e["tool"] for e in unresolved})
        triggers.append({
            "type": "error_alert",
            "severity": "high",
            "detail": (
                f"Hay {len(unresolved)} errores sin resolver "
                f"en las herramientas: {', '.join(tools_affected)}."
            ),
        })
    elif len(unresolved) > 0:
        triggers.append({
            "type": "error_notice",
            "severity": "low",
            "detail": (
                f"Hay {len(unresolved)} error(es) pendiente(s) de revisión."
            ),
        })

    # --- Regla 2: Tareas pendientes envejecidas ---
    pending = signals.get("pending_tasks", [])
    stale_tasks = [
        t for t in pending
        if _is_stale_task(t.get("created_at"), TASK_STALE_HOURS)
    ]
    if stale_tasks:
        triggers.append({
            "type": "stale_tasks",
            "severity": "medium",
            "detail": (
                f"{len(stale_tasks)} tarea(s) llevan más de "
                f"{TASK_STALE_HOURS}h pendientes."
            ),
        })

    # --- Regla 3: Actividad reciente en archivos ---
    recent = signals.get("recent_files", [])
    if recent:
        triggers.append({
            "type": "recent_activity",
            "severity": "info",
            "detail": (
                f"Se detectaron {len(recent)} archivo(s) modificados "
                f"en las últimas {RECENT_FILES_HOURS}h."
            ),
        })

    # --- Regla 4: Alerta si OpenClaw está caído ---
    if not signals.get("openclaw_healthy", True):
        triggers.append({
            "type": "openclaw_offline",
            "severity": "medium",
            "detail": (
                "El servidor primario de orquestación (OpenClaw) está offline. "
                "MILO operará temporalmente usando solo Vulcan (de respaldo)."
            ),
        })

    return triggers


def generate_proactive_message(triggers: list[dict], signals: dict) -> str:
    """Construye un mensaje de sesión proactivo en español a partir de los
    triggers y señales recibidas.

    Args:
        triggers: lista devuelta por evaluate_triggers().
        signals: diccionario devuelto por gather_signals().

    Returns:
        Cadena de texto con el saludo proactivo.
    """
    if not triggers:
        return "✅ Todo en orden, jefe. No detecto problemas pendientes. ¿En qué trabajamos hoy?"

    lines: list[str] = ["🔔 Inicio de sesión — Resumen proactivo de MILO:\n"]

    # Ordenar por severidad para mostrar lo más importante primero
    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    sorted_triggers = sorted(
        triggers, key=lambda t: severity_order.get(t["severity"], 99)
    )

    severity_icons = {
        "high": "🚨",
        "medium": "⚠️",
        "low": "📋",
        "info": "ℹ️",
    }

    for trigger in sorted_triggers:
        icon = severity_icons.get(trigger["severity"], "•")
        lines.append(f"  {icon} {trigger['detail']}")

    # Resumen final
    error_count = len(signals.get("unresolved_errors", []))
    task_count = len(signals.get("pending_tasks", []))
    lines.append(
        f"\n📊 Resumen: {error_count} error(es) | "
        f"{task_count} tarea(s) pendiente(s)."
    )
    lines.append("\n¿Quieres que me encargue de algo primero?")

    return "\n".join(lines)


def get_session_greeting() -> dict:
    """Orquesta el flujo completo de proactividad al inicio de sesión.

    Returns:
        Dict con:
            - greeting (str): mensaje proactivo en español.
            - signals (dict): señales crudas recopiladas.
            - triggers (list): lista de triggers activados.
    """
    signals = gather_signals()
    triggers = evaluate_triggers(signals)
    greeting = generate_proactive_message(triggers, signals)

    logger.info(
        "Saludo de sesión generado con %d trigger(s).", len(triggers)
    )

    return {
        "greeting": greeting,
        "signals": signals,
        "triggers": triggers,
    }


# ---------------------------------------------------------------------------
# Funciones internas de recopilación de señales
# ---------------------------------------------------------------------------

def _get_unresolved_errors() -> list[dict]:
    """Consulta la tabla incidents buscando errores no resueltos."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, timestamp, tool, error FROM incidents WHERE resolved = 0 "
        "ORDER BY timestamp DESC"
    )
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "tool": row["tool"],
            "error": row["error"],
        }
        for row in rows
    ]


def _get_pending_tasks() -> list[dict]:
    """Consulta la tabla task_queue buscando tareas con status 'pending'."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, task_name, created_at, attempts FROM task_queue "
        "WHERE status = 'pending' ORDER BY created_at ASC"
    )
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row["id"],
            "task_name": row["task_name"],
            "created_at": row["created_at"],
            "attempts": row["attempts"],
        }
        for row in rows
    ]


def _get_recently_modified_files() -> list[str]:
    """Escanea el directorio del proyecto en busca de archivos .py modificados
    dentro de la ventana temporal RECENT_FILES_HOURS.

    Usa la variable de entorno PROJECT_ROOT si está disponible, de lo contrario
    intenta inferir la raíz del proyecto.
    """
    project_root = os.getenv("PROJECT_ROOT", ".")
    scan_dir = Path(project_root) / RECENT_FILES_SCAN_DIR
    cutoff = datetime.now() - timedelta(hours=RECENT_FILES_HOURS)
    recent: list[str] = []

    if not scan_dir.exists():
        return recent

    for filepath in scan_dir.rglob("*.py"):
        try:
            mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
            if mtime >= cutoff:
                recent.append(str(filepath))
        except OSError:
            continue

    return sorted(recent)


def _is_stale_task(created_at: str | None, threshold_hours: int) -> bool:
    """Determina si una tarea es 'envejecida' comparando su fecha de creación
    con el umbral dado en horas."""
    if not created_at:
        return False
    try:
        created_dt = datetime.fromisoformat(created_at)
        return datetime.now() - created_dt > timedelta(hours=threshold_hours)
    except (ValueError, TypeError):
        return False

def _check_openclaw_health() -> bool:
    """Verifica si el daemon local de OpenClaw está en ejecución y accesible."""
    import requests
    url = os.getenv("OPENCLAW_URL", "http://127.0.0.1:18789")
    token = os.getenv("OPENCLAW_TOKEN", "")
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.get(url, headers=headers, timeout=1.0)
        # Si logramos conectar y responde (incluso 404), está levantado
        return True
    except Exception:
        return False
