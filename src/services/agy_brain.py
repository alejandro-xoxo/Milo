import subprocess
import logging
import os
import requests
from src.services.db_service import record_tool_failure, reset_tool_failures, log_incident
from src.services.circuit_breaker import check_circuit_breaker, ToolDisabledException

logger = logging.getLogger(__name__)

class AgyBrain:
    """
    Único cerebro de MILO. No usa ninguna API key directamente.
    Toda inferencia pasa por Antigravity CLI (agy) por defecto.
    Si agy falla o está inactivo por cuotas (429), hace failover automático
    a OpenClaw local gateway.
    """

    def __init__(self, project_path: str):
        self.project_path = project_path

    def ask(self, prompt: str, mode: str = "chat", status_callback=None) -> str:
        """
        Envía un prompt a OpenClaw como motor primario. Si falla, hace fallback
        a agy (Vulcan) como motor de respaldo.
        """
        use_vulcan = False
        openclaw_error = ""

        # Reportar estado inicial a la UX
        if status_callback:
            status_callback("Invocando OpenClaw (Default)...")

        # 1. Verificar Circuit Breaker para 'openclaw'
        try:
            check_circuit_breaker("openclaw")
        except ToolDisabledException as tde:
            logger.warning(f"AgyBrain: OpenClaw bloqueado por Circuit Breaker: {tde}")
            use_vulcan = True
            openclaw_error = str(tde)

        # 2. Intentar OpenClaw si no está bloqueado
        if not use_vulcan:
            logger.info("Enviando petición a OpenClaw...")
            openclaw_res = self._ask_openclaw(prompt)
            if openclaw_res:
                # Éxito con OpenClaw: resetear fallos y loguear motor activo
                reset_tool_failures("openclaw")
                self._log_active_engine("openclaw")
                if status_callback:
                    status_callback("Resuelto mediante OpenClaw.")
                return openclaw_res
            else:
                # Falló la llamada HTTP
                logger.warning("Llamada a OpenClaw fallida, preparando fallback a Vulcan...")
                record_tool_failure("openclaw")
                log_incident("openclaw", "Failed to get response from OpenClaw gateway", {"prompt": prompt})
                openclaw_error = "OpenClaw gateway connection failed or returned non-200"
                use_vulcan = True

        # 3. Fallback a agy (Vulcan)
        if use_vulcan:
            if status_callback:
                status_callback("OpenClaw no disponible. Desviando a Vulcan (CLI)...")
            logger.info("Iniciando fallback a Vulcan (agy)...")

            # Verificar Circuit Breaker para 'vulcan'
            try:
                check_circuit_breaker("vulcan")
            except ToolDisabledException as tde:
                logger.error(f"AgyBrain: Ambos motores fallaron. Vulcan bloqueado por Circuit Breaker: {tde}")
                return f"[MILO] No pude completar la solicitud. OpenClaw falló ({openclaw_error}) y Vulcan está bloqueado por Circuit Breaker."

            try:
                result = subprocess.run(
                    ["agy", "--model", "Gemini 3.5 Flash (Medium)", "--dangerously-skip-permissions", "--print", prompt],
                    capture_output=True, 
                    text=True, 
                    timeout=300,
                    cwd=self.project_path
                )

                if result.returncode != 0:
                    logger.error(f"Error en Vulcan (returncode={result.returncode}): {result.stderr}")
                    record_tool_failure("vulcan")
                    log_incident("vulcan", result.stderr.strip(), {"prompt": prompt})
                    return f"[MILO] No pude completar la solicitud. OpenClaw falló ({openclaw_error}) y Vulcan falló con error: {result.stderr.strip()}"
                else:
                    # Éxito con Vulcan
                    reset_tool_failures("vulcan")
                    self._log_active_engine("vulcan")
                    if status_callback:
                        status_callback("Resuelto mediante Vulcan (CLI).")
                    return self._parse_output(result.stdout)

            except Exception as e:
                logger.error(f"Excepción en AgyBrain al invocar Vulcan: {e}")
                record_tool_failure("vulcan")
                log_incident("vulcan", str(e), {"prompt": prompt})
                return f"[MILO] No pude completar la solicitud. OpenClaw falló ({openclaw_error}) y Vulcan falló con excepción: {e}"

    def _ask_openclaw(self, prompt: str) -> str:
        url = os.getenv("OPENCLAW_URL", "http://127.0.0.1:18789")
        token = os.getenv("OPENCLAW_TOKEN", "")
        
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
            
        payload = {
            "model": os.getenv("OPENCLAW_MODEL", "openclaw/default"),
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        
        try:
            logger.info(f"Conectando a OpenClaw en {url}/v1/chat/completions...")
            response = requests.post(f"{url}/v1/chat/completions", json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.info("Respuesta obtenida con éxito desde OpenClaw.")
                return content.strip()
            else:
                logger.error(f"OpenClaw devolvió status {response.status_code}: {response.text}")
                return ""
        except Exception as e:
            logger.error(f"Error de conexión con OpenClaw: {e}")
            return ""

    def _log_active_engine(self, engine_name: str):
        import sqlite3
        from src.services.db_service import get_db_path
        try:
            conn = sqlite3.connect(get_db_path())
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO tool_status (tool_name, failure_count, disabled_until)
            VALUES ('active_engine', 0, ?)
            ON CONFLICT(tool_name) DO UPDATE SET
                disabled_until = excluded.disabled_until
            """, (engine_name,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error logging active engine: {e}")

    def _parse_output(self, raw: str) -> str:
        return raw.strip()

